#
# dashboard.py - streamlit dashboard for httpd coverage comparison
#
# Run with: streamlit run coverage/tools/dashboard.py
#
import json
import os

import altair as alt
import pandas as pd
import streamlit as st

COVERAGE_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# colors
C_PYTHON = "#F0C040"
C_PERL = "#5B9BD5"
C_BOTH = "#3fb950"
C_GRAY = "#484f58"
C_RED = "#f85149"
C_YELLOW = "#d29922"
C_PURPLE = "#bc8cff"

MODULE_NAMES = {
    "server": "Server Core", "aaa": "Auth (AAA)", "http2": "HTTP/2",
    "ssl": "SSL/TLS", "proxy": "Proxy", "http": "HTTP",
    "filters": "Filters", "cache": "Cache", "mappers": "Mappers",
    "md": "ACME/MD", "generators": "Generators", "metadata": "Metadata",
    "loggers": "Loggers", "session": "Session", "lua": "Lua",
    "debugging": "Debugging", "dav": "WebDAV", "core": "Module Core",
    "slotmem": "Shared Memory", "database": "Database", "ldap": "LDAP",
    "cluster": "Cluster", "arch": "Platform",
}


def file_to_module(fpath):
    if fpath.startswith("server/"):
        return "Server Core"
    if fpath.startswith("modules/"):
        parts = fpath.split("/")
        if len(parts) >= 2:
            return MODULE_NAMES.get(parts[1], parts[1].title())
    if fpath.startswith("support/"):
        return "Support Tools"
    if fpath.startswith("os/"):
        return "Platform"
    return "Other"


def basename(path):
    if "/" in path:
        return path.split("/")[-1]
    return path


def suite_file_rows(raw):
    rows = []
    for fname, info in sorted(raw.items()):
        rows.append({
            "Source File": basename(fname),
            "Module": file_to_module(fname),
            "Executable Lines": info["total"],
            "Lines Covered": info["covered"],
            "Coverage %": round(info["covered"] / info["total"] * 100, 1) if info["total"] else 0,
        })
    return rows


def suite_by_module(raw):
    by_module = {}
    for fname, info in raw.items():
        mod = file_to_module(fname)
        e = by_module.setdefault(mod, {"total": 0, "covered": 0})
        e["total"] += info["total"]
        e["covered"] += info["covered"]
    return by_module

# -- data loading --
@st.cache_data
def load_json(path):
    with open(path) as f:
        return json.load(f)


@st.cache_data
def per_file_from_raw(raw_path):
    raw = load_json(raw_path)
    files = {}
    for f in raw["files"]:
        total = len(f["lines"])
        covered = sum(1 for l in f["lines"] if l["count"] > 0)
        files[f["file"]] = {"total": total, "covered": covered}
    return files


@st.cache_data
def load_all():
    py_norm = load_json(os.path.join(COVERAGE_ROOT, "processed", "python.norm.json"))
    perl_norm = load_json(os.path.join(COVERAGE_ROOT, "processed", "perl.norm.json"))
    py_raw = per_file_from_raw(os.path.join(COVERAGE_ROOT, "raw", "python.json"))
    perl_raw = per_file_from_raw(os.path.join(COVERAGE_ROOT, "raw", "perl.json"))

    # gap = lines only perl covers
    gap_path = os.path.join(COVERAGE_ROOT, "metrics", "perl_only.json")
    gap = load_json(gap_path) if os.path.exists(gap_path) else {}

    # python-only lines
    py_only = {}
    for f, lines in py_norm.items():
        perl_set = set(perl_norm.get(f, []))
        diff = [l for l in lines if l not in perl_set]
        if diff:
            py_only[f] = diff

    all_files = set(list(py_norm.keys()) + list(perl_norm.keys()))
    total_instrumentable = sum(v["total"] for v in py_raw.values())
    py_covered = sum(v["covered"] for v in py_raw.values())
    perl_covered = sum(v["covered"] for v in perl_raw.values())
    gap_lines = sum(len(v) for v in gap.values())
    py_only_lines = sum(len(v) for v in py_only.values())

    union_lines = 0
    for f in all_files:
        union_lines += len(set(py_norm.get(f, [])) | set(perl_norm.get(f, [])))
    overlap_lines = py_covered + perl_covered - union_lines

    # per-file comparison table
    file_rows = []
    for fname in sorted(all_files):
        py_info = py_raw.get(fname, {"total": 0, "covered": 0})
        perl_info = perl_raw.get(fname, {"total": 0, "covered": 0})
        total = max(py_info["total"], perl_info["total"])
        py_cov = py_info["covered"]
        perl_cov = perl_info["covered"]
        file_rows.append({
            "Source File": basename(fname),
            "Module": file_to_module(fname),
            "Executable Lines": total,
            "Python Covered": py_cov,
            "Python %": round(py_cov / total * 100, 1) if total else 0,
            "Perl Covered": perl_cov,
            "Perl %": round(perl_cov / total * 100, 1) if total else 0,
            "Difference (Perl - Python)": perl_cov - py_cov,
            "Only in Perl": len(gap.get(fname, [])),
            "Only in Python": len(py_only.get(fname, [])),
        })

    # per-suite file tables
    py_file_rows = suite_file_rows(py_raw)
    perl_file_rows = suite_file_rows(perl_raw)

    # per-module aggregation
    py_by_module = suite_by_module(py_raw)
    perl_by_module = suite_by_module(perl_raw)

    # overlap table
    overlap_rows = []
    for fname in set(py_norm.keys()) & set(perl_norm.keys()):
        ov = len(set(py_norm[fname]) & set(perl_norm[fname]))
        if ov > 0:
            overlap_rows.append({
                "Source File": basename(fname),
                "Module": file_to_module(fname),
                "Lines Both Suites Execute": ov,
            })
    overlap_rows.sort(key=lambda x: -x["Lines Both Suites Execute"])

    # gap table
    gap_rows = []
    for fname, lines in sorted(gap.items(), key=lambda x: -len(x[1])):
        total = max(py_raw.get(fname, {"total": 0})["total"],
                    perl_raw.get(fname, {"total": 0})["total"])
        gap_rows.append({
            "Source File": basename(fname),
            "Lines Only in Perl": len(lines),
            "Executable Lines": total,
            "% of File": round(len(lines) / total * 100, 1) if total else 0,
        })

    return {
        "total_instrumentable": total_instrumentable,
        "py_covered": py_covered,
        "perl_covered": perl_covered,
        "union_lines": union_lines,
        "overlap_lines": overlap_lines,
        "gap_lines": gap_lines,
        "py_only_lines": py_only_lines,
        "py_files": len(py_raw),
        "perl_files": len(perl_raw),
        "all_files": len(all_files),
        "file_table": pd.DataFrame(file_rows),
        "py_file_table": pd.DataFrame(py_file_rows),
        "perl_file_table": pd.DataFrame(perl_file_rows),
        "py_by_module": py_by_module,
        "perl_by_module": perl_by_module,
        "gap_table": pd.DataFrame(gap_rows),
        "overlap_table": pd.DataFrame(overlap_rows),
    }


# -- page setup --

st.set_page_config(page_title="httpd Coverage Comparison", layout="wide")
st.title("httpd Test Coverage")
st.caption("Comparing Python and Perl test suites")

required = [
    os.path.join(COVERAGE_ROOT, "processed", "perl.norm.json"),
    os.path.join(COVERAGE_ROOT, "processed", "python.norm.json"),
    os.path.join(COVERAGE_ROOT, "raw", "perl.json"),
    os.path.join(COVERAGE_ROOT, "raw", "python.json"),
]
missing = [p for p in required if not os.path.exists(p)]
if missing:
    st.error("Missing data files:\n" + "\n".join("- " + p for p in missing) +
             "\n\nSee coverage/README.md for how to generate them.")
    st.stop()

data = load_all()

consolidation_path = os.path.join(COVERAGE_ROOT, "per_test", "perl", "consolidation_ranking.json")
has_consolidation = os.path.exists(consolidation_path)

infra_ratio = {}
if has_consolidation:
    cons_data = load_json(consolidation_path)
    infra_ratio = cons_data.get("file_infra_ratio", {}) if isinstance(cons_data, dict) else {}

tab_overview, tab_python, tab_perl, tab_shared, tab_consolidation = st.tabs([
    "Overview", "Python Focus", "Perl Focus", "Shared Infrastructure", "Consolidation"
])


# -- helpers --

def kpi(label, value, color=None):
    with st.container(border=True):
        st.caption(label)
        if color:
            st.markdown(f"<span style='font-size:1.8rem;font-weight:700;color:{color}'>{value}</span>",
                        unsafe_allow_html=True)
        else:
            st.markdown(f"<span style='font-size:1.8rem;font-weight:700'>{value}</span>",
                        unsafe_allow_html=True)


def bar_chart(df, x_col, y_col, color, height=350, angle=-45):
    chart = alt.Chart(df).mark_bar(
        color=color, cornerRadiusTopLeft=3, cornerRadiusTopRight=3,
    ).encode(
        x=alt.X(f"{x_col}:N", sort=df[x_col].tolist(),
                axis=alt.Axis(labelAngle=angle, title=None)),
        y=alt.Y(f"{y_col}:Q", title=y_col),
        tooltip=list(df.columns),
    ).properties(height=height)
    return chart


def progress_col(name):
    return st.column_config.ProgressColumn(name, min_value=0, max_value=100, format="%.1f%%")


# -- tab 1: overview --

with tab_overview:
    d = data

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi("Executable Lines", f"{d['total_instrumentable']:,}")
    with c2:
        kpi("Covered by any suite", f"{d['union_lines']:,}")
    with c3:
        kpi("Coverage", f"{d['union_lines']/d['total_instrumentable']*100:.1f}%")
    with c4:
        kpi("Both suites hit", f"{d['overlap_lines']:,}", C_BOTH)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi("Python Covered", f"{d['py_covered']:,}", C_PYTHON)
    with c2:
        kpi("Perl Covered", f"{d['perl_covered']:,}", C_PERL)
    with c3:
        kpi("Python Only", f"{d['py_only_lines']:,}", C_PYTHON)
    with c4:
        kpi("Perl Only", f"{d['gap_lines']:,}", C_PERL)

    with st.container(border=True):
        st.subheader("Coverage Breakdown")
        total = d["total_instrumentable"]
        breakdown = pd.DataFrame({
            "Category": ["Both suites", "Python only", "Perl only", "Untested"],
            "Lines": [d["overlap_lines"], d["py_only_lines"], d["gap_lines"],
                      total - d["union_lines"]],
        })
        breakdown["Pct"] = (breakdown["Lines"] / total * 100).round(1)
        breakdown["Label"] = breakdown["Category"] + " - " + breakdown["Pct"].astype(str) + "%"

        donut = alt.Chart(breakdown).mark_arc(innerRadius=80, outerRadius=160).encode(
            theta="Lines:Q",
            color=alt.Color("Label:N", scale=alt.Scale(
                domain=breakdown["Label"].tolist(),
                range=[C_BOTH, C_PYTHON, C_PERL, C_GRAY],
            ), legend=alt.Legend(title=None, orient="right", labelFontSize=14, symbolSize=200)),
            tooltip=["Category", alt.Tooltip("Pct:Q", format=".1f"), alt.Tooltip("Lines:Q", format=",")],
        ).properties(height=420)
        st.altair_chart(donut, width="stretch")

    with st.container(border=True):
        st.subheader("Per-File Comparison")
        st.dataframe(
            d["file_table"], width="stretch", hide_index=True,
            column_config={"Python %": progress_col("Python %"), "Perl %": progress_col("Perl %")},
        )


# -- suite focus tab (reused for python and perl) --

def render_focus(df_all, by_module, color, name):
    df = df_all.copy()

    if infra_ratio:
        df["_infra"] = df["Source File"].map(lambda f: infra_ratio.get(f, 0))
        excluded = len(df[df["_infra"] > 80])
        df = df[df["_infra"] <= 80].drop(columns=["_infra"])
        st.caption(f"{len(df)} module-specific files ({excluded} infrastructure files excluded)")

    df = df.sort_values("Lines Covered", ascending=False)

    with st.container(border=True):
        st.subheader(f"{name} coverage by module")
        mod_rows = []
        for mod, info in sorted(by_module.items(), key=lambda x: -x[1]["covered"]):
            pct = round(info["covered"] / info["total"] * 100, 1) if info["total"] else 0
            mod_rows.append({"Module": mod, "Executable Lines": info["total"],
                             "Lines Covered": info["covered"], "Coverage %": pct})
        df_mod = pd.DataFrame(mod_rows)
        df_chart = df_mod[df_mod["Lines Covered"] > 0].head(15)
        st.altair_chart(bar_chart(df_chart, "Module", "Lines Covered", color), width="stretch")
        st.dataframe(df_mod, width="stretch", hide_index=True,
                     column_config={"Coverage %": progress_col("Coverage %")})

    with st.container(border=True):
        st.subheader(f"{name} coverage by file")
        st.altair_chart(
            bar_chart(df.head(25), "Source File", "Lines Covered", color, angle=-60),
            width="stretch")
        st.dataframe(df, width="stretch", hide_index=True,
                     column_config={"Coverage %": progress_col("Coverage %")})


# -- tab 2: python focus --

with tab_python:
    d = data
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi("Lines Covered", f"{d['py_covered']:,}", C_PYTHON)
    with c2:
        kpi("Coverage", f"{d['py_covered']/d['total_instrumentable']*100:.1f}%")
    with c3:
        kpi("Files Touched", str(d["py_files"]))
    with c4:
        kpi("Python-Only Lines", f"{d['py_only_lines']:,}", C_PYTHON)
    render_focus(d["py_file_table"], d["py_by_module"], C_PYTHON, "Python")


# -- tab 3: perl focus --

with tab_perl:
    d = data
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi("Lines Covered", f"{d['perl_covered']:,}", C_PERL)
    with c2:
        kpi("Coverage", f"{d['perl_covered']/d['total_instrumentable']*100:.1f}%")
    with c3:
        kpi("Files Touched", str(d["perl_files"]))
    with c4:
        kpi("Perl-Only Lines", f"{d['gap_lines']:,}", C_PERL)
    render_focus(d["perl_file_table"], d["perl_by_module"], C_PERL, "Perl")


# -- tab 4: shared infrastructure --

with tab_shared:
    d = data
    st.markdown(
        "Both suites execute the same C code - this is not duplication. "
        "This tab shows why the overlap exists."
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi("Lines both hit", f"{d['overlap_lines']:,}", C_BOTH)
    with c2:
        kpi("% of covered", f"{d['overlap_lines']/d['union_lines']*100:.1f}%" if d['union_lines'] else "0%")
    untested = d["total_instrumentable"] - d["union_lines"]
    with c3:
        kpi("Untested", f"{untested:,}")
    with c4:
        kpi("% untested", f"{untested/d['total_instrumentable']*100:.1f}%")

    with st.container(border=True):
        st.subheader("Why overlap?")
        st.markdown(
            "**Server core** - every request goes through core.c, event.c, protocol.c, "
            "request.c etc. regardless of what the test targets.\n\n"
            "**Default-loaded modules** - modules like mod_rewrite and mod_proxy are "
            "loaded by both frameworks. Python H2 tests use RewriteRule as plumbing, "
            "not to test rewriting."
        )

    core_files = {
        "core.c", "event.c", "config.c", "http_filters.c", "protocol.c",
        "request.c", "http_protocol.c", "util.c", "util_filter.c",
        "scoreboard.c", "log.c", "vhost.c", "mpm_common.c", "mpm_fdqueue.c",
    }

    df_overlap = d["overlap_table"]

    with st.container(border=True):
        st.subheader("Top shared files")
        df_ov20 = df_overlap.head(20).copy()
        df_ov20["Type"] = df_ov20["Source File"].apply(
            lambda f: "Server core" if f in core_files else "Module (loaded by both)")
        chart = alt.Chart(df_ov20).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
            x=alt.X("Source File:N", sort=df_ov20["Source File"].tolist(),
                     axis=alt.Axis(labelAngle=-60, title=None)),
            y=alt.Y("Lines Both Suites Execute:Q", title="Lines both suites run"),
            color=alt.Color("Type:N", scale=alt.Scale(
                domain=["Server core", "Module (loaded by both)"],
                range=[C_BOTH, C_PERL])),
            tooltip=["Source File", "Lines Both Suites Execute", "Type"],
        ).properties(height=350)
        st.altair_chart(chart, width="stretch")

    with st.container(border=True):
        st.subheader("Shared by module")
        ov_by_mod = {}
        for row in df_overlap.to_dict("records"):
            mod = row.get("Module", "Other")
            ov_by_mod[mod] = ov_by_mod.get(mod, 0) + row["Lines Both Suites Execute"]
        ov_rows = [{"Module": m, "Shared Lines": n}
                   for m, n in sorted(ov_by_mod.items(), key=lambda x: -x[1])]
        if ov_rows:
            df_ov_mod = pd.DataFrame(ov_rows)
            st.altair_chart(
                bar_chart(df_ov_mod.head(12), "Module", "Shared Lines", C_BOTH, 300),
                width="stretch")

    if infra_ratio:
        with st.container(border=True):
            st.subheader("Infrastructure ratio by file")
            st.caption(
                "What % of each file's covered lines are shared infrastructure "
                "(hit by >25% of all Perl tests). 100% = pure infrastructure."
            )
            infra_rows = [{"Source File": f, "Infrastructure %": r}
                          for f, r in sorted(infra_ratio.items(), key=lambda x: -x[1])]
            st.dataframe(
                pd.DataFrame(infra_rows), width="stretch", hide_index=True,
                column_config={"Infrastructure %": progress_col("Infrastructure %")},
            )


# -- tab 5: consolidation --

with tab_consolidation:
    d = data

    if not has_consolidation:
        st.warning(
            "No consolidation data. Generate it with:\n\n"
            "```\npython3 coverage/tools/analyze_consolidation.py \\\n"
            "    coverage/per_test/perl/norm coverage/processed/python.norm.json \\\n"
            "    --json coverage/per_test/perl/consolidation_ranking.json\n```"
        )
    else:
        cons = load_json(consolidation_path)
        if isinstance(cons, list):
            ranking = cons
            gap_by_file = []
        else:
            ranking = cons.get("ranking", [])
            gap_by_file = cons.get("gap_by_file", [])

        df_rank = pd.DataFrame(ranking)
        contributing = df_rank[df_rank["new_lines"] > 0].copy()
        contributing["test"] = contributing["test"].str.replace("__", "/")
        has_split = "module_lines" in contributing.columns
        contributing = contributing.reset_index(drop=True)
        contributing.index += 1
        contributing.index.name = "Rank"
        redundant = len(df_rank) - len(contributing)

        thresholds = {}
        for t in (50, 80, 90, 95, 99, 100):
            for i, e in enumerate(ranking, 1):
                if e["pct"] >= t:
                    thresholds[t] = i
                    break

        # gap overview
        with st.container(border=True):
            st.subheader("The coverage gap")
            st.caption(f"Perl covers {d['gap_lines']:,} lines that Python does not.")

            col_left, col_right = st.columns(2)
            with col_left:
                df_gap = d["gap_table"]
                st.altair_chart(
                    bar_chart(df_gap.head(20), "Source File", "Lines Only in Perl", C_RED, angle=-60),
                    width="stretch")

            with col_right:
                top10 = df_gap.head(10)
                rest = df_gap.iloc[10:]["Lines Only in Perl"].sum() if len(df_gap) > 10 else 0
                donut_data = []
                colors = [C_RED, C_PERL, C_YELLOW, "#e3b341", "#58a6ff",
                          C_PURPLE, "#f778ba", C_BOTH, "#56d364", "#79c0ff", C_GRAY]
                for _, row in top10.iterrows():
                    donut_data.append({"File": row["Source File"], "Lines": row["Lines Only in Perl"]})
                if rest > 0:
                    donut_data.append({"File": "All others", "Lines": rest})
                df_donut = pd.DataFrame(donut_data)
                donut = alt.Chart(df_donut).mark_arc(innerRadius=55, outerRadius=120).encode(
                    theta="Lines:Q",
                    color=alt.Color("File:N", scale=alt.Scale(
                        domain=df_donut["File"].tolist(),
                        range=colors[:len(df_donut)]),
                        legend=alt.Legend(title=None, orient="right", columns=1)),
                    tooltip=["File", alt.Tooltip("Lines:Q", format=",")],
                ).properties(height=350)
                st.altair_chart(donut, width="stretch")

        # cumulative closure curve
        with st.container(border=True):
            st.subheader("How fast does the gap close?")

            cols = st.columns(6)
            for i, t in enumerate((50, 80, 90, 95, 99, 100)):
                if t in thresholds:
                    with cols[i]:
                        with st.container(border=True):
                            st.caption(f"{t}% after")
                            st.markdown(f"**{thresholds[t]} tests**")

            curve = contributing[["test", "pct"]].copy()
            curve["rank"] = range(1, len(curve) + 1)
            area = alt.Chart(curve).mark_area(
                color=C_PERL, opacity=0.15,
                line={"color": C_PERL, "strokeWidth": 2},
            ).encode(
                x=alt.X("rank:Q", title="Tests migrated",
                         scale=alt.Scale(domain=[1, len(curve)])),
                y=alt.Y("pct:Q", title="Gap closed %",
                         scale=alt.Scale(domain=[0, 100])),
                tooltip=["test", "rank", "pct"],
            ).properties(height=350)
            st.altair_chart(area, width="stretch")

        # ranking table
        with st.container(border=True):
            st.subheader("Migration ranking")
            st.caption(f"{len(df_rank)} tests total, {len(contributing)} contribute new lines.")

            display_cols = {
                "test": "Perl Test", "new_lines": "New Gap Lines",
                "cumulative": "Cumulative", "pct": "Gap Closed %",
            }
            col_config = {
                "Gap Closed %": progress_col("Gap Closed %"),
            }

            if has_split:
                display_cols["module_lines"] = "Module-Specific"
                display_cols["infra_lines"] = "Shared Infra"
                contributing["Key Modules"] = contributing["top_module_files"].apply(
                    lambda files: ", ".join(f"{f['file']} ({f['lines']})" for f in files)
                    if isinstance(files, list) else "")
                display_cols["Key Modules"] = "Key Modules"

            display = contributing.rename(columns=display_cols)[list(display_cols.values())]
            st.dataframe(display, width="stretch", column_config=col_config)

        # gap by source file
        if gap_by_file:
            with st.container(border=True):
                st.subheader("Gap by source file")
                df_gf = pd.DataFrame(gap_by_file)
                df_gf["file"] = df_gf["file"].apply(basename)
                df_gf["top_test"] = df_gf["top_test"].str.replace("__", "/")
                df_gf = df_gf.rename(columns={
                    "file": "Source File", "gap_lines": "Lines Only in Perl",
                    "num_tests": "Perl Tests", "top_test": "Top Test",
                })
                st.dataframe(df_gf.head(30), width="stretch", hide_index=True)

        # overlap analysis
        overlap_data = cons.get("overlap", []) if isinstance(cons, dict) else []
        if overlap_data:
            with st.container(border=True):
                st.subheader("Python overlap with Perl tests")
                st.caption(
                    "For each Perl test: how much of its focused code "
                    "(lines hit by few tests) does Python already cover?"
                )

                df_ov = pd.DataFrame(overlap_data)
                df_ov["test"] = df_ov["test"].str.replace("__", "/")

                high = len(df_ov[df_ov["overlap_percentage"] >= 80])
                low = len(df_ov[df_ov["overlap_percentage"] < 30])
                fully = len(df_ov[df_ov["unique_focused"] == 0])
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    kpi("Tests", str(len(df_ov)))
                with c2:
                    kpi(">=80% overlap", str(high), C_BOTH)
                with c3:
                    kpi("<30% overlap", str(low), C_RED)
                with c4:
                    kpi("Fully covered", str(fully), C_BOTH)

            with st.container(border=True):
                df_ov["band"] = df_ov["overlap_percentage"].apply(
                    lambda p: ">=80%" if p >= 80 else ("<30%" if p < 30 else "30-80%"))
                scatter = alt.Chart(df_ov).mark_circle(size=60).encode(
                    x=alt.X("focused_lines:Q", title="Focused lines",
                             scale=alt.Scale(type="log")),
                    y=alt.Y("overlap_percentage:Q", title="% covered by Python",
                             scale=alt.Scale(domain=[0, 100])),
                    color=alt.Color("band:N", scale=alt.Scale(
                        domain=[">=80%", "30-80%", "<30%"],
                        range=[C_BOTH, C_GRAY, C_RED])),
                    tooltip=["test", "focused_lines", "python_overlap", "overlap_percentage", "unique_focused"],
                ).properties(height=400)

                rule80 = alt.Chart(pd.DataFrame({"y": [80]})).mark_rule(
                    strokeDash=[4, 4], color=C_BOTH).encode(y="y:Q")
                rule30 = alt.Chart(pd.DataFrame({"y": [30]})).mark_rule(
                    strokeDash=[4, 4], color=C_RED).encode(y="y:Q")
                st.altair_chart(scatter + rule80 + rule30, width="stretch")

            with st.container(border=True):
                st.subheader("Overlap detail")
                df_show = df_ov.sort_values("overlap_percentage", ascending=True).copy()
                df_show["Top Targets"] = df_show["top_focused_files"].apply(
                    lambda files: ", ".join(f"{f['file']} ({f['lines']})" for f in files)
                    if isinstance(files, list) else "")
                df_show = df_show.rename(columns={
                    "test": "Perl Test", "focused_lines": "Focused Lines",
                    "python_overlap": "Python Covers", "overlap_percentage": "Overlap %",
                    "unique_focused": "Unique to Perl",
                })
                st.dataframe(
                    df_show[["Perl Test", "Focused Lines", "Python Covers",
                             "Overlap %", "Unique to Perl", "Top Targets"]],
                    width="stretch", hide_index=True,
                    column_config={"Overlap %": progress_col("Overlap %")},
                )
