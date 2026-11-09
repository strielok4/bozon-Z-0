from pathlib import Path
import numpy as np
import pandas as pd
from dataset_config import ASSETS_DIR, DATASET, DEBUG_DIR
e_cm = 91.1876  # GeV; approximate center-of-mass energy

pd.set_option("display.max_columns", None)
MAX_EVENT_ENERGY = 110.0  # GeV; retain events at the threshold.

COLUMNS = [
    "nEvt",
    "Total.Px", "Total.Py", "Total.Pz", "Total.E", "Total.M",
    "nElectron", "nMuon", "nJet",
    "ID1", "P1.Px", "P1.Py", "P1.Pz", "P1.E", "P1.M",
    "ID2", "P2.Px", "P2.Py", "P2.Pz", "P2.E", "P2.M",
    "ID3", "P3.Px", "P3.Py", "P3.Pz", "P3.E", "P3.M",
]


def save_df(df, filename="output.csv"):
    path = DEBUG_DIR/filename
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    print(f"Saved DataFrame to file: {filename}")


def add_kinematics(df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    """Store event momentum or object angles required by the classifier."""
    px = df[f"{prefix}.Px"]
    py = df[f"{prefix}.Py"]
    pz = df[f"{prefix}.Pz"]
    pt = np.sqrt(px**2 + py**2)
    p = np.sqrt(px**2 + py**2 + pz**2)

    if prefix == "Total":
        df["Total.P"] = p
        df["Total.Pt"] = pt
    elif prefix in ("P1", "P2"):
        df[f"{prefix}.Theta"] = np.where(p > 0, np.arctan2(pt, pz), np.nan)
        # Preserve the existing azimuth convention: zero along the Y axis.
        df[f"{prefix}.Phi"] = np.where(pt > 0, np.arctan2(px, py), np.nan)
    return df


def add_pair_features(df):
    """Store only the object summaries used by the active templates."""
    df["P.M.min"] = df[["P1.M", "P2.M"]].min(axis=1)
    df["P.M.max"] = df[["P1.M", "P2.M"]].max(axis=1)
    df["P.E.max"] = df[["P1.E", "P2.E"]].max(axis=1)
    df["P.E.min"] = df[["P1.E", "P2.E"]].min(axis=1)

    electron_energies = pd.concat(
        [df[f"P{i}.E"].where(df[f"ID{i}"].eq(1)) for i in (1, 2, 3)],
        axis=1,
    )
    df["e.E.max"] = electron_energies.max(axis=1)
    jet_mass = pd.concat(
        [df[f"P{i}.M"].where(df[f"ID{i}"].eq(3)) for i in (1, 2, 3)],
        axis=1,
    )
    df["j.M.max"] = jet_mass.max(axis=1)
    return df


def load_sample(path,sample:str):
    # Validate original rows before selection, including rows that will be rejected.
    with Path(path).open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            fields = line.split()
            if not fields:
                continue
            if len(fields) != len(COLUMNS):
                raise ValueError(f"{path}:{line_number}: expected {len(COLUMNS)} columns, got {len(fields)}")
            try:
                values = [float(value) for value in fields]
            except ValueError as exc:
                raise ValueError(f"{path}:{line_number}: invalid numeric value") from exc
            if not np.isfinite(values).all():
                raise ValueError(f"{path}:{line_number}: NaN or infinite value")
    df = pd.read_csv(
        path,
        sep=r"\s+",
        names=COLUMNS,
    )
    df['sample'] = sample
    return df


def filter_events(data: pd.DataFrame, max_energy=MAX_EVENT_ENERGY, remove_empty=True):
    """Return a selected copy without changing input rows, event IDs or files."""
    keep = data["Total.E"].le(max_energy)
    if remove_empty:
        keep &= data["ID1"].ne(0)
    return data.loc[keep].copy().reset_index(drop=True)


def read_data(files):
    df = pd.concat([load_sample(files[sample],sample) for sample in files.keys()], ignore_index=True)
    for prefix in ["Total", "P1", "P2"]:
        df = add_kinematics(df, prefix)
    return df


def correct_channel_counts(A_df, observed_counts, true_labels):
    """Solve A x = y and propagate Poisson count covariance, without reporting."""
    y = observed_counts
    A = A_df.to_numpy(dtype=float)
    y_vec = y.to_numpy(dtype=float)

    det = np.linalg.det(A)
    cond = np.linalg.cond(A)


    if abs(det) < 1e-12:
        x_hat, *_ = np.linalg.lstsq(A, y_vec, rcond=None)
        A_inv = np.linalg.pinv(A)
    else:
        x_hat = np.linalg.solve(A, y_vec)
        A_inv = np.linalg.inv(A)

    # Do not automatically clip negative estimates:
    # retain the raw correction result when solving the system directly.
    result = pd.DataFrame({
        "channel": list(true_labels),
        "corrected_count": x_hat,
    })

    channel_names = {
        "h": "Z -> hadrons",
        "e": "Z -> e+ e-",
        "m": "Z -> mu+ mu-",
        "t": "Z -> tau+ tau-",
        "n": "background / noise",
        "nu": "Z -> neutrino anti-neutrino",
    }

    result["recognized_channel"] = result["channel"].map(channel_names)

    # --- Uncertainties of the corrected counts ---
    # Poisson approximation: V_obs = diag(N_obs)
    V_obs = np.diag(y_vec)
    V_true = A_inv @ V_obs @ A_inv.T
    sigma_counts = np.sqrt(np.diag(V_true))

    result["sigma_corrected_count"] = sigma_counts

    diagnostics = {"determinant": det, "condition_number": cond,
                   "used_least_squares": abs(det) < 1e-12}
    return result, V_true, diagnostics


def calculate_branching_fractions(counts, covariance, invisible_fraction_assumed=0.20):
    """Return corrected visible/full fractions and their propagated uncertainties."""
    result = counts.copy()
    V_true = covariance
    # --- Visible Z decays: h/e/m/t, excluding background n ---
    visible_z_channels = ["h", "e", "m", "t"]
    z_mask = result["channel"].isin(visible_z_channels)

    total_visible_z = result.loc[z_mask, "corrected_count"].sum()

    result["fraction_visible_Z"] = np.nan
    result["percent_visible_Z"] = np.nan
    result["sigma_fraction_visible_Z"] = np.nan
    result["sigma_percent_visible_Z"] = np.nan

    if total_visible_z > 0:
        # Propagate fraction uncertainties through the normalization:
        # f_i = x_i / sum_j x_j
        # V_f = J V_x J^T

        z_indices = np.where(z_mask.to_numpy())[0]

        x_visible = result.loc[z_mask, "corrected_count"].to_numpy(dtype=float)
        V_visible = V_true[np.ix_(z_indices, z_indices)]

        S = x_visible.sum()
        f_visible = x_visible / S

        n_vis = len(f_visible)
        J = np.zeros((n_vis, n_vis))

        for i in range(n_vis):
            for j in range(n_vis):
                delta = 1.0 if i == j else 0.0
                J[i, j] = (delta - f_visible[i]) / S

        V_fraction = J @ V_visible @ J.T

        sigma_fraction_visible = np.sqrt(np.diag(V_fraction))
        sigma_percent_visible = 100 * sigma_fraction_visible

        result.loc[z_mask, "fraction_visible_Z"] = f_visible
        result.loc[z_mask, "percent_visible_Z"] = 100 * f_visible
        result.loc[z_mask, "sigma_fraction_visible_Z"] = sigma_fraction_visible
        result.loc[z_mask, "sigma_percent_visible_Z"] = sigma_percent_visible


    # --- Full Z decay distribution with an assumed invisible fraction ---
    # Note: n represents background/noise, not a Z decay channel.
    # The Z distribution includes h/e/m/t and the externally assumed nu channel.
    visible_fraction_assumed = 1.0 - invisible_fraction_assumed

    br_full = result.loc[z_mask, [
        "channel",
        "recognized_channel",
        "corrected_count",
        "sigma_corrected_count",
        "fraction_visible_Z",
        "percent_visible_Z",
        "sigma_fraction_visible_Z",
        "sigma_percent_visible_Z",
    ]].copy()

    br_full["fraction_full_assuming_invisible"] = (
            br_full["fraction_visible_Z"] * visible_fraction_assumed
    )

    br_full["percent_full_assuming_invisible"] = (
            100 * br_full["fraction_full_assuming_invisible"]
    )

    br_full["sigma_fraction_full_assuming_invisible"] = (
            br_full["sigma_fraction_visible_Z"] * visible_fraction_assumed
    )

    br_full["sigma_percent_full_assuming_invisible"] = (
            100 * br_full["sigma_fraction_full_assuming_invisible"]
    )


    neutrino_row = pd.DataFrame([{
        "channel": "nu",
        "recognized_channel": "Z -> neutrino anti-neutrino",
        "corrected_count": np.nan,
        "sigma_corrected_count": np.nan,
        "fraction_visible_Z": np.nan,
        "percent_visible_Z": np.nan,
        "sigma_fraction_visible_Z": np.nan,
        "sigma_percent_visible_Z": np.nan,
        "fraction_full_assuming_invisible": invisible_fraction_assumed,
        "percent_full_assuming_invisible": 100 * invisible_fraction_assumed,
        "sigma_fraction_full_assuming_invisible": np.nan,
        "sigma_percent_full_assuming_invisible": np.nan,
    }])


    br_full = pd.concat([br_full, neutrino_row], ignore_index=True)

    return result, br_full


def calculate_sample_prediction_tables(data):
    """Calculate uncorrected S tables once, using binomial fraction errors."""
    sample_s = data[data["sample"] == "s"].copy()
    if sample_s.empty:
        return None
    s_all = (
        sample_s["class_auto"]
        .value_counts(dropna=False)
        .rename_axis("predicted")
        .reset_index(name="count")
    )
    s_all["percent_all"] = 100 * s_all["count"] / s_all["count"].sum()

    z_channels = ["h", "e", "m", "t"]
    s_z = sample_s[sample_s["class_auto"].isin(z_channels)]
    total_z_recognized = len(s_z)
    br = (
        s_z["class_auto"]
        .value_counts()
        .reindex(z_channels, fill_value=0)
        .rename_axis("channel")
        .reset_index(name="count")
    )

    if total_z_recognized > 0:
        br["fraction"] = br["count"] / total_z_recognized
        br["percent"] = 100 * br["fraction"]

        br["sigma_fraction"] = np.sqrt(
            br["fraction"] * (1 - br["fraction"]) / total_z_recognized
        )
        br["sigma_percent"] = 100 * br["sigma_fraction"]
    else:
        br["fraction"] = np.nan
        br["percent"] = np.nan
        br["sigma_fraction"] = np.nan
        br["sigma_percent"] = np.nan


    br_visible = br.rename(columns={
        "fraction": "fraction_visible", "percent": "percent_visible",
        "sigma_fraction": "sigma_fraction_visible", "sigma_percent": "sigma_percent_visible",
    }).copy()
    # --- Rescale for comparison with tabulated full branching fractions ---
    # Comparing with full Z branching fractions requires an assumed invisible fraction.
    # The assumed fraction for all neutrino channels combined is approximately 20%.
    invisible_fraction_assumed = 0.20
    visible_fraction_assumed = 1.0 - invisible_fraction_assumed

    br_full = br_visible.copy()
    br_full["fraction_full_assuming_invisible"] = (
            br_full["fraction_visible"] * visible_fraction_assumed
    )
    br_full["percent_full_assuming_invisible"] = (
            100 * br_full["fraction_full_assuming_invisible"]
    )

    br_full["sigma_fraction_full_assuming_invisible"] = (
            br_full["sigma_fraction_visible"] * visible_fraction_assumed
    )
    br_full["sigma_percent_full_assuming_invisible"] = (
            100 * br_full["sigma_fraction_full_assuming_invisible"]
    )

    neutrino_row = pd.DataFrame([{
        "channel": "nu",
        "count": np.nan,
        "fraction_visible"  : np.nan,
        "percent_visible": np.nan,
        "sigma_fraction_visible": np.nan,
        "sigma_percent_visible": np.nan,
        "fraction_full_assuming_invisible": invisible_fraction_assumed,
        "percent_full_assuming_invisible": 100 * invisible_fraction_assumed,
        "sigma_fraction_full_assuming_invisible": np.nan,
        "sigma_percent_full_assuming_invisible": np.nan,
    }])

    br_full = pd.concat([br_full, neutrino_row], ignore_index=True)


    n_noise = (sample_s["class_auto"] == "n").sum()
    n_ambiguous = (sample_s["class_auto"] == "ambiguous").sum()
    return {
        "all_predictions": s_all, "visible": br_visible,
        "full": br_full, "visible_count": total_z_recognized,
        "noise_count": n_noise, "ambiguous_count": n_ambiguous,
        "total_count": len(sample_s),
    }


class ZClassifier:

    def __init__(self, data: pd.DataFrame):
        """Store input data; call run() to classify and generate reports."""
        self.data = data
        self.sample_s_ambiguous_as_background = 0

    def run(self):
        """Classify events and report results."""
        self.data = add_pair_features(self.data)
        self.apply_initial_rules()
        self.data['P1P2.angle3D'] = np.nan
        self.apply_topology_templates()
        mask = self.data["class_auto"] == "ambiguous"
        self.sample_s_ambiguous_as_background = int(
            (mask & self.data["sample"].eq("s")).sum()
        )
        self.data.loc[mask, "class_auto"] = "n"
        self.report_reference_accuracy()
        self.report_sample_predictions()
        self.compute_corrected_s_counts()
        save_df(self.data, "final_res.csv")
        return self

    def apply_topology_templates(self):
        """Apply each topology configuration"""
        self.fit_and_apply_templates(
            min_gap=1,
            channels = ('t','h','m','e','n'),
            topology = [0, 0, 2],
            features = ["Total.E","Total.P","Total.M","Total.Pt","P.M.min","P.M.max","P.E.max","P1P2.angle3D"]
        )
        self.fit_and_apply_templates(
            min_gap=1,
            channels=( 'n', 'e', 't'),
            topology=[2, 0, 0],
            features=["Total.E", "Total.M","P.E.min", "P.E.max"]
        )
        self.fit_and_apply_templates(
            min_gap=1,
            channels=('m', 'n',  't'),
            topology=[0, 2, 0],
            features=["Total.E", "Total.P",  "Total.M", "Total.Pt", "P1P2.angle3D"]
        )
        self.fit_and_apply_templates(
            min_gap=1,
            channels=('m', 't'),
            topology=[1, 1, 0],
            features=["Total.E", "Total.P", "Total.M", "Total.Pt", "P1P2.angle3D"]
        )
        self.fit_and_apply_templates(
            min_gap=1,
            channels=("t", "n", "e"),
            topology=[1, 0, 0],
            features=["Total.E", "Total.P", "Total.M", "Total.Pt"]
        )
        self.fit_and_apply_templates(
            min_gap=1,
            channels=("t", "m"),
            topology=[0, 1, 0],
            features=["Total.E", "Total.P",  "Total.Pt"]
        )
        self.fit_and_apply_templates(
            min_gap=1,
            channels=("t", "n", "h", "e", "m"),
            topology=[0, 0, 1],
            features=["Total.E", "Total.P", "Total.M", "Total.Pt"]
        )
        self.fit_and_apply_templates(
            min_gap=1,
            channels=("t", "e", "n"),
            topology=[1, 0, 1],
            features=["Total.E", "Total.M", "Total.Pt", "j.M.max", 'e.E.max']
        )
        self.fit_and_apply_templates(
            min_gap=1,
            channels=("t", "n", "h", "e", "m"),
            topology=[0, 0, 0],
            features=["Total.E", "Total.M", "Total.P", "Total.Pt"]
        )
        self.fit_and_apply_templates(
            min_gap=1,
            channels=("t", "m"),
            topology=[0, 1, 1],
            features=["Total.E", "Total.P", "Total.M", "Total.Pt", "P1P2.angle3D"]
        )

    def build_response_matrix(
            self,
            true_labels=("h", "e", "m", "t"),
            pred_labels=None,
            true_col="sample",
            pred_col="class_auto",
    ):
        if pred_labels is None:
            pred_labels = list(true_labels)

        # Include only:
        # 1. true channels included in the correction,
        # 2. predicted classes included in the matrix.
        #
        # Classes such as "n" or "ambiguous" can therefore be excluded
        # from the matrix normalization when absent from pred_labels.
        test = self.data[
            self.data[true_col].isin(true_labels)
            & self.data[pred_col].isin(pred_labels)
            ].copy()

        # Counts: rows = predicted class, columns = true class
        counts = pd.crosstab(
            test[pred_col],
            test[true_col]
        ).reindex(
            index=pred_labels,
            columns=true_labels,
            fill_value=0
        )

        # Normalize each column:
        # A[predicted, true] = P(predicted | true)
        col_sums = counts.sum(axis=0)

        A_df = counts.div(
            col_sums.replace(0, np.nan),
            axis=1
        ).fillna(0.0)

        print("\nCounts used to construct the classification matrix:")
        print(counts)

        print("\nClassification matrix A = P(predicted | true), normalized by column:")
        print(A_df)

        print("\nColumn sums of matrix A:")
        print(A_df.sum(axis=0))

        return A_df

    def compute_corrected_s_counts(
            self,
            true_labels=("h", "e", "m", "t", "n"),
            pred_labels=("h", "e", "m", "t", "n"),
            true_col="sample",
            pred_col="class_auto",
            invisible_fraction_assumed=0.20,
    ):
        A_df = self.build_response_matrix(
            true_labels=true_labels,
            pred_labels=pred_labels,
            true_col=true_col,
            pred_col=pred_col,
        )

        sample_s = self.data[self.data[true_col] == "s"].copy()

        y = (
            sample_s[pred_col]
            .value_counts()
            .reindex(pred_labels, fill_value=0)
            .astype(float)
        )

        counts, covariance, diagnostics = correct_channel_counts(A_df, y, true_labels)
        result, br_full = calculate_branching_fractions(
            counts, covariance, invisible_fraction_assumed
        )
        self.report_corrected_results(result, br_full, diagnostics)
        return result, br_full

    def report_corrected_results(self, result, br_full, diagnostics):
        """Print and save corrected results"""
        det = diagnostics["determinant"]
        cond = diagnostics["condition_number"]
        print(f"\ndet(A) = {det}")
        print(f"cond(A) = {cond}")
        if diagnostics["used_least_squares"]:
            print("Matrix A is singular or nearly singular — using least squares.")
        print("\nCorrected sample S counts — direct solution:")
        print(result)
        print("\nCorrected Z branching fractions with an assumed invisible fraction:")
        print(br_full)
        save_df(br_full,"res_after_matrix.csv")
        # --- Report background separately ---
        background = result[result["channel"] == "n"].copy()

        print("\nEstimated background/noise after classification-matrix correction:")
        print(background)


    def report_reference_accuracy(self):
        """Report accuracy and the confusion matrix on labeled references."""
        true_col = "sample"
        pred_col = "class_auto"
        test = self.data[self.data[true_col] != 's'].copy()
        test["_correct"] = test[true_col] == test[pred_col]
        overall = 100 * test["_correct"].mean()

        by_sample = (
            test
            .groupby(true_col)["_correct"]
            .agg(
                count="size",
                correct="sum",
                accuracy_percent=lambda x: 100 * x.mean()
            )
            .reset_index()
        )

        confusion = pd.crosstab(
            test[true_col],
            test[pred_col],
            rownames=["true"],
            colnames=["predicted"],
            margins=True
        )

        print(f"Reference-sample accuracy: {overall:.2f}%")
        print("\nAccuracy by sample:")
        print(by_sample)
        print("\nConfusion matrix:")
        print(confusion)

    def report_sample_predictions(self):
        """Report S counts and uncorrected branching fractions once."""
        summary = calculate_sample_prediction_tables(self.data)
        if summary is None:
            return
        s_all = summary["all_predictions"]
        br_visible = summary["visible"]
        br_full = summary["full"]
        total_visible_z = summary["visible_count"]
        n_noise = summary["noise_count"]
        n_ambiguous = summary["ambiguous_count"]
        n_total = summary["total_count"]

        print("\nSample S — all predictions:")
        print(s_all)
        print(f"Total number of events in sample S: {n_total}")
        print(f"Total events classified as visible Z decays in sample S: {total_visible_z}")
        print(f"Events classified as background/noise n: {n_noise}")
        print(
            "Of these, ambiguous events assigned to background: "
            f"{self.sample_s_ambiguous_as_background}"
        )
        print(f"Events still classified as ambiguous: {n_ambiguous}")
        print("\nVisible Z branching fractions, excluding background n and ambiguous predictions:")
        print(br_visible)
        print("\nZ branching fractions rescaled to the full distribution with an assumed invisible fraction:")
        print(br_full)


    def write_topology_statistics(self, data = None, name = "missing_ET.csv"):
        if data is None:
            data = self.data
        counts = (
            data
            .groupby(["sample", "nElectron", "nMuon", "nJet", ])
            .size()
            .reset_index(name="count")
        )

        counts["fraction"] = counts["count"] / counts.groupby("sample")["count"].transform("sum")
        counts["percent"] = 100 * counts["fraction"]

        save_df(counts, "topology_counts.csv")
        missing_e_by_combo = (
            data
            .groupby(["sample", "nElectron", "nMuon", "nJet"])
            .agg(
                count=("Total.E", "size"),
                mean_missing_E=("Total.E", lambda energy: (e_cm - energy).mean()),
                median_missing_E=("Total.E", lambda energy: (e_cm - energy).median()),
                std_missing_E=("Total.E", lambda energy: (e_cm - energy).std()),
                min_missing_E=("Total.E", lambda energy: (e_cm - energy).min()),
                max_missing_E=("Total.E", lambda energy: (e_cm - energy).max()),
                mean_missing_P=("Total.P", "mean"),
                median_missing_P=("Total.P", "median"),
                std_missing_P=("Total.P", "std"),
                min_missing_P=("Total.P", "min"),
                max_missing_P=("Total.P", "max"),
                mean_total_M=("Total.M", "mean"),
                median_total_M=("Total.M", "median"),
                std_total_M=("Total.M", "std"),
                min_total_M=("Total.M", "min"),
                max_total_M=("Total.M", "max"),
                mean_Total_Pt=("Total.Pt", "mean"),
                median_Total_Pt=("Total.Pt", "median"),
                std_Total_Pt = ("Total.Pt", "std"),
                min_Total_Pt = ("Total.Pt", "min"),
                max_Total_Pt = ("Total.Pt", "max"),
                mean_max_PM = ("P.M.max", "mean"),
                median_max_PM = ("P.M.max", "median"),
                std_max_PM = ("P.M.max", "std"),
                mean_min_PM=("P.M.min", "mean"),
                median_min_PM=("P.M.min", "median"),
                std_min_PM=("P.M.min", "std"),

            )
            .reset_index()
            .sort_values(["sample", "count"], ascending=[True, False])
        )
        save_df(missing_e_by_combo,name)


    def angular_separation(self,df: pd.DataFrame, a = "1", b = "2"):
        """Compute the 3D angle between two object directions using Theta and Phi.

        a, b: object prefixes, such as "P1" and "P2".

        Return the angle in radians:
        0  -> objects point in the same direction
        pi -> objects point in opposite directions"""

        theta1 = df[f"{a}.Theta"]
        theta2 = df[f"{b}.Theta"]

        phi1 = df[f"{a}.Phi"]
        phi2 = df[f"{b}.Phi"]

        dphi = phi1 - phi2

        cos_angle = (
                np.cos(theta1) * np.cos(theta2)
                + np.sin(theta1) * np.sin(theta2) * np.cos(dphi)
        )
        cos_angle = np.clip(cos_angle, -1.0, 1.0)
        angle = np.arccos(cos_angle)
        return angle

    def classify_electron_rule(self,row):
        if self.amount_clasified == 2 :
            if self.e == 1 and self.j == 1:
                if abs((e_cm - row["Total.E"])) <= 3 and abs(self.angle - np.pi) <= np.deg2rad(10):
                    return ('e', 'clear e+e-')
            elif self.e == 2:
                if abs((e_cm - row["Total.E"])) <= 18 and abs(self.angle - np.pi) <= np.deg2rad(1):
                    return ('e', 'clear e+e-')
        return 0

    def classify_muon_rule(self,row):
        if self.amount_clasified == 2:
            if (self.mu == 1 and self.j == 1) or self.mu == 2:
                if abs((e_cm - row["Total.E"])) <= 6 and abs(self.angle - np.pi) <= np.deg2rad(10):
                    return ('m' , 'clear mu+mu-')
        return 0
    def classify_hadron_rule(self,row):
        if (self.amount_clasified == self.j and self.amount_clasified >=3 ):
            if abs((e_cm - row["Total.E"])) <= 45:
                return ('h', 'clear hadron')
        return 0
    def classify_background_rule(self,row):
        if row["Total.E"] <= 9:
            return ('n', 'clear_noise')
        if self.amount_clasified == 2:
            if abs(self.angle) <= np.deg2rad(90):
                return ('n', 'clear_noise')
        return 0


    def classify_by_rules(self,row):
        out = {0}
        self.e = row["nElectron"]
        self.mu = row['nMuon']
        self.j = row['nJet']
        self.amount_clasified= self.e + self.mu + self.j
        if self.amount_clasified == 2:
            self.angle = self.angular_separation(row, "P1", "P2")

        out.add(self.classify_muon_rule(row))
        out.add(self.classify_electron_rule(row))
        out.add(self.classify_hadron_rule(row))
        out.add(self.classify_background_rule(row))
        if out == {0}:
            return "ambiguous", "not classified by clear rules"
        out.remove(0)
        if len(out) >1:
            return "ambiguous", "not classified by clear rules"
        else:
            for x in out:
                return x[0],x[1]


    def apply_initial_rules(self):
        res = self.data.apply(self.classify_by_rules, axis=1, result_type='expand')
        self.data[["class_auto","class_reason"]] = res
        save_df(self.data,'test.csv')


    def is_clear_zero_object_noise(self, row):
        return (
                row["nElectron"] == 0
                and row["nMuon"] == 0
                and row["nJet"] == 0
                and row["Total.M"] < 15
                and (
                        row["Total.E"] < 20
                        or (
                                row["Total.E"] < 35
                                and row["Total.Pt"] < 4
                        )
                )
        )

    def fit_robust_template(self, reference_events, features):
        """Return feature scales/medians, or None when a template cannot be fitted."""
        if reference_events.empty or not features:
            return None
        mad_floor = 1e-6
        feature_scales = {}
        feature_medians = {}
        for feature in features:
            values = np.asarray(reference_events[feature])
            if not np.isfinite(values).any():
                return None
            median = np.nanmedian(values)
            if not np.isfinite(median):
                return None
            mad = np.nanmedian(np.abs(values - median))
            if not np.isfinite(mad):
                return None
            if mad < mad_floor:
                mad = mad_floor
            # Convert MAD to a Gaussian-equivalent standard-deviation scale.
            feature_scales[feature] = mad * 1.4826
            if not np.isfinite(feature_scales[feature]):
                return None
            feature_medians[feature] = median
        return feature_scales, feature_medians

    def fit_and_apply_templates(
        self, min_gap, channels=('h', 't'), topology=(0, 1, 0),
        features=("P1P2.angle3D",),
    ):
        """Fit channel templates and classify selected ambiguous events."""
        selected_samples = list(channels) + ["s"]
        candidate_channels = [channel for channel in channels if channel != "s"]
        selected_mask = (
            self.data["sample"].isin(selected_samples)
            & self.data["nElectron"].eq(topology[0])
            & self.data["nMuon"].eq(topology[1])
            & self.data["nJet"].eq(topology[2])
            & self.data["class_auto"].eq("ambiguous")
        )
        selected_events = self.data.loc[selected_mask].copy()
        if selected_events.empty:
            return
        if "P1P2.angle3D" in features:
            angles = selected_events.apply(
                lambda row: self.angular_separation(row, "P1", "P2"),
                axis=1, result_type="expand",
            )
            self.data.loc[selected_mask, "P1P2.angle3D"] = angles
            selected_events.loc[:, "P1P2.angle3D"] = angles

        templates = {}
        for channel in candidate_channels:
            reference_events = selected_events.loc[selected_events["sample"] == channel]
            template = self.fit_robust_template(reference_events, features)
            if template is None:
                print(
                    f"Skipping unavailable template: channel={channel}, "
                    f"topology={tuple(topology)}, reference_events={len(reference_events)}"
                )
                continue
            templates[channel] = template

        predictions = selected_events.apply(
            lambda row: self.classify_by_robust_score(
                row, candidate_channels, templates, features, min_gap
            ),
            axis=1, result_type="expand",
        )
        predictions.columns = ["class_auto", "class_reason"]
        self.data.loc[selected_mask, ["class_auto", "class_reason"]] = predictions


    def classify_by_robust_score(self, row, channels, templates, features, min_gap):
        if self.is_clear_zero_object_noise(row):
            return "n", "clear 0-object noise"
        scores = {}

        for channel in channels:
            template = templates.get(channel)
            if template is None:
                continue
            feature_scales, feature_medians = template
            if not all(
                np.isfinite(feature_medians[feature])
                and np.isfinite(feature_scales[feature])
                and feature_scales[feature] > 0
                for feature in features
            ):
                continue
            score = 0
            with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
                for feature in features:
                    standardized_deviation = (
                        (row[feature] - feature_medians[feature]) / feature_scales[feature]
                    )
                    score += standardized_deviation ** 2
            if np.isfinite(score):
                scores[channel] = score

        if not scores:
            return "ambiguous", "no valid template score"
        if len(scores) == 1:
            channel, score = next(iter(scores.items()))
            return str(channel), f"only valid template: {channel}; robust score: {score}"

        sorted_scores = sorted(scores.items(), key=lambda item: item[1])
        best_channel, best_score = sorted_scores[0]
        second_best_score = sorted_scores[1][1]
        gap = second_best_score - best_score
        if gap < min_gap:
            return "ambiguous", f"robust scores close: {scores}"
        return str(best_channel), f"robust score: {best_score}"


def main():
    print(f"Dataset: {DATASET}")
    FILE_ANALYSIS = ASSETS_DIR / "sample_for_analysis.dat"
    FILE_HADRONY = ASSETS_DIR / "sm_lep90_pythia6_test_qq.dat"
    FILE_TAU = ASSETS_DIR / "sm_lep90_pythia6_test_tata.dat"
    FILE_MU = ASSETS_DIR / "sm_lep90_pythia6_test_mumu.dat"
    FILE_E = ASSETS_DIR / "sm_lep90_pythia6_test_ee.dat"
    FILE_NOISE = ASSETS_DIR / "sm_lep90_pythia6_test_bg.dat"
    FILES = {"h": FILE_HADRONY,
             "e": FILE_E,
             "m": FILE_MU,
             "t": FILE_TAU,
             "n": FILE_NOISE,
             "s": FILE_ANALYSIS,
             }
    data = read_data(FILES)
    if DATASET == "delphes":
        selected_data = data
        print(f"Event filtering disabled for Delphes: using all {len(data)} events")
    else:
        selected_data = filter_events(data)
        print(f"Event selection: kept {len(selected_data)} / {len(data)}; rejected {len(data) - len(selected_data)}")
    work = ZClassifier(selected_data)
    work.run()
    work.write_topology_statistics()

if __name__ == '__main__':
    main()

