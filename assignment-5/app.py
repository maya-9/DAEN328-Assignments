# importing libraries from practice_app.py
import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import create_engine, text

# db config
DB_NAME = "EmployeeDB"
DB_USER = "postgres"
DB_PASSWORD = "CStat547300_."      
DB_HOST = "localhost"
DB_PORT = "5432"

# setup ---------------------------------------------------------------------------------
# page config
st.set_page_config(page_title="Employee Database", layout="wide")

# title
st.title("Employee Database Dashboard")

#cache
@st.cache_resource
def get_engine():
    return create_engine(
        f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

# run queries 
@st.cache_data(ttl=600)
def q(sql, params=None):
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


# 1 - sidebar -----------------------------------------------------------------------------
# title
st.sidebar.header("Filters")

# filters
all_divs = q("SELECT divtype FROM divisions ORDER BY divtype;")["divtype"].tolist()
all_depts = q("SELECT departmentname FROM departments ORDER BY departmentname;")["departmentname"].tolist()
sal_min, sal_max = q("SELECT MIN(salary), MAX(salary) FROM employeedetails;").iloc[0].astype(float)

# slidebars
chosen_divs = st.sidebar.multiselect("Divisions", all_divs, default = all_divs)
chosen_depts = st.sidebar.selectbox("Departments", ["All"] + all_depts)
chosen_sals = st.sidebar.slider("Salary", sal_min, sal_max, (sal_min,sal_max))

# failsafe
if not chosen_divs: 
    st.warning("Pick at least one division in the sidebar.")
    st.stop()

# filter ---------------------------------------------------------------------------------
# conditions
FILTER_SQL = """
    FROM employeedetails e
    JOIN personaldetails    p ON e.ssn = p.ssn
    JOIN departments      dpt ON e.departmentid = dpt.departmentid
    JOIN divisions        div ON e.divisionid = div.divisionid
    JOIN jobtitles          t ON e.jobtitleid = t.jobtitleid
    WHERE div.divtype = ANY(:divs)
        AND (:dpts = 'All' OR dpt.departmentname = :dpts)
        AND e.salary BETWEEN :sal_min AND :sal_max
"""

#parameters
params = {"divs": chosen_divs, "dpts": chosen_depts, 
          "sal_min": chosen_sals[0], "sal_max": chosen_sals[1]}


# 2 - KPI row ----------------------------------------------------------------------------
# filtering desired numbers
kpi = q("""
    SELECT COUNT(*) AS employees,
    AVG(e.salary) as avg_sal,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY e.salary) AS med_sal"""
    + FILTER_SQL, params,
)

# if there are no employees, a message is raised
if kpi.loc[0, "employees"] == 0:
    st.info("No employees match these filters.")
    st.stop()

# creating kpi row
c1, c2, c3 = st.columns(3)
c1.metric("Headcount", f"{kpi.loc[0, 'employees']:,}")
c2.metric("Average Salary", f"{kpi.loc[0, 'avg_sal']:,.2f}")
c3.metric("Median Salary", f"{kpi.loc[0, 'med_sal']:,.2f}")


# 3 - bar chart - headcount by dpt ---------------------------------------------------------
# filtering by dept
dpt_pop = q("SELECT dpt.departmentname, COUNT(*) AS population " + FILTER_SQL +
              " GROUP BY dpt.departmentname ORDER BY population DESC;", params)

# making bar chart 
st.subheader("Headcount by department")
if dpt_pop.empty:
    st.info("No headcount matches these filters.")
else: 
    fig = px.bar(dpt_pop, x="population", y="departmentname",
        title="Headcount by department",
        labels={"population": "Headcount", "departmentname": "Department"})
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, width="stretch")


# 5 - bar chart - average salary by age ------------------------------------------------------
# making divisions
left, right = st.columns(2)

# filtering
age = "EXTRACT(YEAR FROM AGE(CURRENT_DATE, p.birthdate))"
age_sal = q(
    f"SELECT CASE WHEN {age} < 30 THEN 'Under 30' "
    f"            WHEN {age} < 40 THEN '30-39' "
    f"            WHEN {age} < 50 THEN '40-49' "
    f"            WHEN {age} < 60 THEN '50-59' "
    f"            ELSE '60+' "
    f"       END AS age_band, "
    f"       COUNT(*) AS employees, "
    f"       ROUND(AVG(e.salary), 2) AS avg_salary "
    + FILTER_SQL +
    " AND p.birthdate IS NOT NULL "
    " AND p.birthdate <> '1900-01-01' "
    " GROUP BY age_band;",
    params,
)
order = ["Under 30", "30-39", "40-49", "50-59", "60+"]

# making bar chart 
with left:
    st.subheader("Average salary by age")
    if age_sal.empty:
        st.info("No employee ages fit these filters.")
    else:
        fig = px.bar(age_sal, x="age_band", y="avg_salary", text="employees",
                    category_orders={"age_band": order},
                    title="Average salary by age",
                    labels={"age_band": "Age range", "avg_salary": "Average salary ($)",
                            "employees": "Employees"})
        st.plotly_chart(fig, width="stretch")


# 6 - ten job titles by average salary

job_avg = q("SELECT t.jobtitle, ROUND(AVG(e.salary),2) as avg_salary " + FILTER_SQL +
            "GROUP BY t.jobtitle "
            "ORDER BY avg_salary DESC "
            "LIMIT 10;", params)

# making bar chart 
with right:
    st.subheader("Average salary by job title")
    if job_avg.empty:
        st.info("No salaries fit these filters.")
    else:
        fig = px.bar(job_avg, x="avg_salary", y="jobtitle",
                    orientation='h',
                    title="Average salary by job title",
                    labels={"jobtitle": "Job Title", "avg_salary": "Average salary ($)"})
        fig.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig, width="stretch")

# 4 - box plot - salary distriibution ----------------------------------------------------------
# filtering salary by div
div_sal = q("SELECT div.divtype, e.salary" + FILTER_SQL + ";", params)

# making boxplot
st.subheader("Salary distribution by division")
if div_sal.empty: 
    st.info("No salary range fits the filters.")
else: 
    fig = px.box(div_sal, x = "salary", y = "divtype",
                 orientation='h',
                 title = "Salary distribution by division",
                 labels = {"divtype": "", "Salary": "Salary range"})
    st.plotly_chart(fig)


# 4 - expander - employee table ----------------------------------------------------------
with st.expander("Show matching employees"):
    emps = q(
        "SELECT p.name, t.jobtitle, dpt.departmentname, div.divtype, e.salary"
        + FILTER_SQL + "ORDER BY e.salary DESC", params
    )
    if emps.empty: st.info("No employees fits the filters.")
    else:
        st.dataframe(emps, width="stretch", hide_index=True)



