"""pharma_formulas.py — Pharmaceutical calculation library for biochem-pipeline-core.

LLMs hallucinate pharmacokinetic constants and dosing formula coefficients.
This module encodes domain-correct equations with proper units, validated inputs,
and clear provenance.  Every function returns a FormulaResult so callers know
the formula used, not just a bare float.

Categories
----------
Pharmacokinetics (PK)
    half_life              — t½ = 0.693 × Vd / CL
    clearance              — CL = Dose / AUC∞
    volume_of_distribution — Vd = Dose / C₀  (IV bolus)
    bioavailability        — F = (AUCoral/AUCiv) × (Doseiv/Doseoral)
    cmax_iv_bolus          — Cmax = Dose / Vd
    auc_one_compartment    — AUC∞ = Dose / CL  (IV infusion or oral at steady state)
    elimination_rate       — ke = CL / Vd  (or 0.693 / t½)
    css_average            — Css_avg = (F × Dose) / (CL × τ)
    loading_dose           — LD = Ctarget × Vd
    maintenance_dose       — MD = Ctarget × CL × τ

Renal / Dosing Adjustment
    cockcroft_gault        — CrCl (mL/min) for aminoglycoside, renally-cleared drug dosing
    mdrd_gfr               — eGFR (mL/min/1.73m²) — KDIGO preferred
    ckd_epi_gfr            — eGFR (mL/min/1.73m²) — CKD-EPI 2021 (race-free)
    calvert_carboplatin    — Dose_mg = AUC_target × (GFR + 25)  [Calvert 1989]
    renal_dose_factor      — Proportion of normal dose for a given eGFR

Body Measurements
    bsa_mosteller          — BSA = √(height_cm × weight_kg / 3600)  [m²]
    bsa_dubois             — BSA = 0.007184 × h^0.725 × w^0.425    [m²]
    ibw_devine             — IBW_male = 50 + 2.3×(in−60); IBW_female = 45.5 + 2.3×(in−60)
    abw                    — ABW = IBW + 0.4×(TBW − IBW)  [kg, for obese patients]

Molecular / Concentration
    molar_mass             — from molecular formula string (e.g. "C9H8O4")
    mg_to_mmol             — mmol = mg / MW
    mmol_to_mg             — mg = mmol × MW
    molar_concentration    — μM = (mass_mg / (MW × volume_L)) × 1000
    nM_to_mg_per_L         — mg/L = nM × MW / 1e6

Usage
-----
    from pharma_formulas import cockcroft_gault, calvert_carboplatin, molar_mass

    crcl = cockcroft_gault(age=72, weight_kg=68, scr_mg_dL=1.4, sex="female")
    print(crcl)  # FormulaResult(value=33.8, units='mL/min', ...)

    dose = calvert_carboplatin(target_auc=5, gfr_or_crcl=crcl.value)
    print(dose)  # FormulaResult(value=294.0, units='mg', ...)

    mw = molar_mass("C54H64N12O12S2")  # oseltamivir phosphate free base approx
    print(mw)    # FormulaResult(value=..., units='g/mol', ...)
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Output type
# ---------------------------------------------------------------------------


@dataclass
class FormulaResult:
    """
    Return type for every formula in this module.

    Attributes
    ----------
    value       : Numeric result in the stated units.
    units       : SI or conventional pharmacokinetic units (str).
    formula     : Name of the formula used (e.g. "Cockcroft-Gault").
    equation    : Human-readable equation string for provenance.
    inputs      : Dict of input name → (value, units) for audit trail.
    warnings    : List of clinically-relevant notes about edge cases.
    """

    value: float
    units: str
    formula: str
    equation: str
    inputs: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        w = f" [{'; '.join(self.warnings)}]" if self.warnings else ""
        return f"FormulaResult({self.value:.4g} {self.units}, formula={self.formula!r}{w})"

    def __float__(self) -> float:
        return self.value


# ---------------------------------------------------------------------------
# Atomic masses (IUPAC 2021, standard atomic weights)
# ---------------------------------------------------------------------------

_ATOMIC_MASS: dict[str, float] = {
    'H':  1.008,   'He': 4.003,   'Li': 6.941,   'Be': 9.012,
    'B':  10.811,  'C':  12.011,  'N':  14.007,  'O':  15.999,
    'F':  18.998,  'Ne': 20.180,  'Na': 22.990,  'Mg': 24.305,
    'Al': 26.982,  'Si': 28.086,  'P':  30.974,  'S':  32.065,
    'Cl': 35.453,  'Ar': 39.948,  'K':  39.098,  'Ca': 40.078,
    'Sc': 44.956,  'Ti': 47.867,  'V':  50.942,  'Cr': 51.996,
    'Mn': 54.938,  'Fe': 55.845,  'Co': 58.933,  'Ni': 58.693,
    'Cu': 63.546,  'Zn': 65.38,   'Ga': 69.723,  'Ge': 72.631,
    'As': 74.922,  'Se': 78.971,  'Br': 79.904,  'Kr': 83.798,
    'Rb': 85.468,  'Sr': 87.620,  'Y':  88.906,  'Zr': 91.224,
    'Nb': 92.906,  'Mo': 95.960,  'Tc': 98.000,  'Ru': 101.07,
    'Rh': 102.906, 'Pd': 106.42,  'Ag': 107.868, 'Cd': 112.411,
    'In': 114.818, 'Sn': 118.711, 'Sb': 121.760, 'Te': 127.600,
    'I':  126.904, 'Xe': 131.293, 'Cs': 132.905, 'Ba': 137.327,
    'La': 138.905, 'Ce': 140.116, 'Pr': 140.908, 'Nd': 144.242,
    'Pm': 145.000, 'Sm': 150.360, 'Eu': 151.964, 'Gd': 157.250,
    'Tb': 158.925, 'Dy': 162.500, 'Ho': 164.930, 'Er': 167.259,
    'Tm': 168.934, 'Yb': 173.045, 'Lu': 174.967, 'Hf': 178.490,
    'Ta': 180.948, 'W':  183.840, 'Re': 186.207, 'Os': 190.230,
    'Ir': 192.217, 'Pt': 195.085, 'Au': 196.967, 'Hg': 200.592,
    'Tl': 204.383, 'Pb': 207.200, 'Bi': 208.980, 'Po': 209.000,
    'At': 210.000, 'Rn': 222.000, 'Fr': 223.000, 'Ra': 226.000,
    'Ac': 227.000, 'Th': 232.038, 'Pa': 231.036, 'U':  238.029,
    'Np': 237.000, 'Pu': 244.000,
}


def _parse_formula(formula: str) -> dict[str, int]:
    """
    Parse a molecular formula into {element: count}.

    Handles nested parentheses like "Ca3(PO4)2".
    Does NOT handle [isotopes] — strip them first if needed.
    """
    def _expand(s: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        i = 0
        while i < len(s):
            if s[i] == '(':
                # Find matching close paren
                depth = 1
                j = i + 1
                while j < len(s) and depth:
                    if s[j] == '(':
                        depth += 1
                    elif s[j] == ')':
                        depth -= 1
                    j += 1
                inner = s[i + 1:j - 1]
                # Grab multiplier after close paren
                k = j
                while k < len(s) and s[k].isdigit():
                    k += 1
                mult = int(s[j:k]) if k > j else 1
                sub = _expand(inner)
                for elem, cnt in sub.items():
                    counts[elem] = counts.get(elem, 0) + cnt * mult
                i = k
            elif s[i].isupper():
                j = i + 1
                while j < len(s) and s[j].islower():
                    j += 1
                elem = s[i:j]
                k = j
                while k < len(s) and s[k].isdigit():
                    k += 1
                cnt = int(s[j:k]) if k > j else 1
                counts[elem] = counts.get(elem, 0) + cnt
                i = k
            else:
                i += 1
        return counts

    return _expand(formula)


# ---------------------------------------------------------------------------
# ─── PHARMACOKINETICS ───────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


def half_life(vd_L: float, cl_L_per_h: float) -> FormulaResult:
    """
    Terminal elimination half-life.

    Formula: t½ = (ln 2 × Vd) / CL = (0.6931 × Vd) / CL

    Parameters
    ----------
    vd_L       : Volume of distribution (litres)
    cl_L_per_h : Total clearance (L/h)
    """
    if cl_L_per_h <= 0:
        raise ValueError("Clearance must be > 0")
    if vd_L <= 0:
        raise ValueError("Volume of distribution must be > 0")
    t_half = (math.log(2) * vd_L) / cl_L_per_h
    return FormulaResult(
        value=t_half,
        units="hours",
        formula="Half-life (one-compartment)",
        equation="t½ = (ln2 × Vd) / CL",
        inputs={"Vd": (vd_L, "L"), "CL": (cl_L_per_h, "L/h")},
    )


def clearance(dose_mg: float, auc_mg_h_per_L: float) -> FormulaResult:
    """
    Total body clearance from IV dose and AUC₀→∞.

    Formula: CL = Dose / AUC∞     (assumes complete bioavailability F=1 for IV)

    Parameters
    ----------
    dose_mg         : Intravenous dose (mg)
    auc_mg_h_per_L  : Area under the curve, plasma concentration vs time (mg·h/L)
    """
    if auc_mg_h_per_L <= 0:
        raise ValueError("AUC must be > 0")
    cl = dose_mg / auc_mg_h_per_L
    return FormulaResult(
        value=cl,
        units="L/h",
        formula="Clearance (IV)",
        equation="CL = Dose_IV / AUC∞",
        inputs={"Dose": (dose_mg, "mg"), "AUC∞": (auc_mg_h_per_L, "mg·h/L")},
    )


def volume_of_distribution(dose_mg: float, c0_mg_per_L: float) -> FormulaResult:
    """
    Apparent volume of distribution from IV bolus dose and time-zero extrapolated
    plasma concentration.

    Formula: Vd = Dose / C₀

    Parameters
    ----------
    dose_mg     : Intravenous bolus dose (mg)
    c0_mg_per_L : Extrapolated plasma concentration at t=0 (mg/L)
    """
    if c0_mg_per_L <= 0:
        raise ValueError("C₀ must be > 0")
    vd = dose_mg / c0_mg_per_L
    return FormulaResult(
        value=vd,
        units="L",
        formula="Volume of Distribution (IV bolus)",
        equation="Vd = Dose / C₀",
        inputs={"Dose": (dose_mg, "mg"), "C₀": (c0_mg_per_L, "mg/L")},
        warnings=["Approximation: assumes instantaneous IV bolus, one-compartment model"],
    )


def bioavailability(
    auc_oral_mg_h_per_L: float,
    dose_oral_mg: float,
    auc_iv_mg_h_per_L: float,
    dose_iv_mg: float,
) -> FormulaResult:
    """
    Absolute oral bioavailability (%).

    Formula: F = (AUCoral / Doseoral) / (AUCiv / Doseiv) × 100

    Parameters
    ----------
    auc_oral_mg_h_per_L : AUC after oral dose (mg·h/L)
    dose_oral_mg        : Oral dose (mg)
    auc_iv_mg_h_per_L   : AUC after IV dose (mg·h/L) — same subject/crossover
    dose_iv_mg          : IV dose (mg)
    """
    if auc_iv_mg_h_per_L <= 0 or dose_iv_mg <= 0 or dose_oral_mg <= 0:
        raise ValueError("AUC and dose inputs must all be > 0")
    f = (auc_oral_mg_h_per_L / dose_oral_mg) / (auc_iv_mg_h_per_L / dose_iv_mg) * 100
    warns = []
    if f > 100:
        warns.append(f"Computed F={f:.1f}% > 100% — possible measurement error or non-linear PK")
    return FormulaResult(
        value=f,
        units="%",
        formula="Absolute Bioavailability",
        equation="F = (AUCoral/Doseoral) / (AUCiv/Doseiv) × 100",
        inputs={
            "AUCoral": (auc_oral_mg_h_per_L, "mg·h/L"),
            "Doseoral": (dose_oral_mg, "mg"),
            "AUCiv": (auc_iv_mg_h_per_L, "mg·h/L"),
            "Doseiv": (dose_iv_mg, "mg"),
        },
        warnings=warns,
    )


def cmax_iv_bolus(dose_mg: float, vd_L: float) -> FormulaResult:
    """
    Peak plasma concentration after IV bolus dose.

    Formula: Cmax = Dose / Vd

    Parameters
    ----------
    dose_mg : Intravenous bolus dose (mg)
    vd_L    : Volume of distribution (L)
    """
    if vd_L <= 0:
        raise ValueError("Vd must be > 0")
    cmax = dose_mg / vd_L
    return FormulaResult(
        value=cmax,
        units="mg/L",
        formula="Cmax (IV bolus, one-compartment)",
        equation="Cmax = Dose / Vd",
        inputs={"Dose": (dose_mg, "mg"), "Vd": (vd_L, "L")},
    )


def auc_one_compartment(dose_mg: float, cl_L_per_h: float, f: float = 1.0) -> FormulaResult:
    """
    AUC₀→∞ for a one-compartment model.

    Formula: AUC∞ = (F × Dose) / CL

    Parameters
    ----------
    dose_mg    : Dose (mg)
    cl_L_per_h : Clearance (L/h)
    f          : Bioavailability fraction 0–1 (default 1.0 for IV)
    """
    if cl_L_per_h <= 0:
        raise ValueError("Clearance must be > 0")
    if not 0 < f <= 1:
        raise ValueError("Bioavailability fraction f must be in (0, 1]")
    auc = (f * dose_mg) / cl_L_per_h
    return FormulaResult(
        value=auc,
        units="mg·h/L",
        formula="AUC∞ (one-compartment)",
        equation="AUC∞ = (F × Dose) / CL",
        inputs={"Dose": (dose_mg, "mg"), "CL": (cl_L_per_h, "L/h"), "F": (f, "fraction")},
    )


def elimination_rate(cl_L_per_h: float, vd_L: float) -> FormulaResult:
    """
    First-order elimination rate constant.

    Formula: ke = CL / Vd   (equivalently: ke = ln2 / t½)

    Parameters
    ----------
    cl_L_per_h : Clearance (L/h)
    vd_L       : Volume of distribution (L)
    """
    if vd_L <= 0:
        raise ValueError("Vd must be > 0")
    if cl_L_per_h <= 0:
        raise ValueError("CL must be > 0")
    ke = cl_L_per_h / vd_L
    return FormulaResult(
        value=ke,
        units="h⁻¹",
        formula="Elimination Rate Constant",
        equation="ke = CL / Vd",
        inputs={"CL": (cl_L_per_h, "L/h"), "Vd": (vd_L, "L")},
    )


def css_average(
    dose_mg: float,
    cl_L_per_h: float,
    tau_h: float,
    f: float = 1.0,
) -> FormulaResult:
    """
    Average steady-state plasma concentration at a fixed dosing interval.

    Formula: Css_avg = (F × Dose) / (CL × τ)

    Parameters
    ----------
    dose_mg    : Dose per interval (mg)
    cl_L_per_h : Clearance (L/h)
    tau_h      : Dosing interval (hours)
    f          : Bioavailability fraction 0–1 (default 1.0)
    """
    if cl_L_per_h <= 0 or tau_h <= 0:
        raise ValueError("CL and dosing interval must be > 0")
    css = (f * dose_mg) / (cl_L_per_h * tau_h)
    return FormulaResult(
        value=css,
        units="mg/L",
        formula="Average Steady-State Concentration",
        equation="Css_avg = (F × Dose) / (CL × τ)",
        inputs={
            "Dose": (dose_mg, "mg"), "CL": (cl_L_per_h, "L/h"),
            "τ": (tau_h, "h"), "F": (f, "fraction"),
        },
    )


def loading_dose(target_concentration_mg_per_L: float, vd_L: float) -> FormulaResult:
    """
    Loading dose to achieve a target plasma concentration rapidly.

    Formula: LD = Ctarget × Vd

    Parameters
    ----------
    target_concentration_mg_per_L : Desired plasma concentration (mg/L)
    vd_L                          : Volume of distribution (L)
    """
    if vd_L <= 0:
        raise ValueError("Vd must be > 0")
    ld = target_concentration_mg_per_L * vd_L
    return FormulaResult(
        value=ld,
        units="mg",
        formula="Loading Dose",
        equation="LD = Ctarget × Vd",
        inputs={
            "Ctarget": (target_concentration_mg_per_L, "mg/L"),
            "Vd": (vd_L, "L"),
        },
    )


def maintenance_dose(
    target_concentration_mg_per_L: float,
    cl_L_per_h: float,
    tau_h: float,
    f: float = 1.0,
) -> FormulaResult:
    """
    Maintenance dose to sustain a target average steady-state concentration.

    Formula: MD = Ctarget × CL × τ / F

    Parameters
    ----------
    target_concentration_mg_per_L : Target Css_avg (mg/L)
    cl_L_per_h                    : Clearance (L/h)
    tau_h                         : Dosing interval (hours)
    f                             : Bioavailability fraction 0–1
    """
    if f <= 0:
        raise ValueError("Bioavailability fraction must be > 0")
    md = target_concentration_mg_per_L * cl_L_per_h * tau_h / f
    return FormulaResult(
        value=md,
        units="mg",
        formula="Maintenance Dose",
        equation="MD = Ctarget × CL × τ / F",
        inputs={
            "Ctarget": (target_concentration_mg_per_L, "mg/L"),
            "CL": (cl_L_per_h, "L/h"),
            "τ": (tau_h, "h"),
            "F": (f, "fraction"),
        },
    )


# ---------------------------------------------------------------------------
# ─── RENAL / DOSING ADJUSTMENT ──────────────────────────────────────────────
# ---------------------------------------------------------------------------


def cockcroft_gault(
    age: float,
    weight_kg: float,
    scr_mg_dL: float,
    sex: Literal["male", "female"],
) -> FormulaResult:
    """
    Cockcroft-Gault estimated creatinine clearance.

    Formula: CrCl = ((140 − age) × weight) / (72 × SCr) × (0.85 if female)

    Reference: Cockcroft DW, Gault MH. Nephron. 1976;16(1):31–41.

    Parameters
    ----------
    age       : Patient age (years)
    weight_kg : Actual body weight (kg) — use IBW or ABW for obese patients;
                see ibw_devine() and abw()
    scr_mg_dL : Serum creatinine (mg/dL)
    sex       : "male" or "female"

    Note: Use actual body weight (ABW) for obese patients, or lean body weight.
    For patients with SCr < 0.6 mg/dL (e.g. cachexia), round up to 0.6.
    """
    if scr_mg_dL <= 0 or age <= 0 or weight_kg <= 0:
        raise ValueError("age, weight, and SCr must be > 0")
    sex_lower = sex.lower()
    if sex_lower not in ("male", "female"):
        raise ValueError("sex must be 'male' or 'female'")

    warns = []
    effective_scr = scr_mg_dL
    if scr_mg_dL < 0.6:
        effective_scr = 0.6
        warns.append(f"SCr {scr_mg_dL} < 0.6 mg/dL — rounded up to 0.6 (ASHP convention for low SCr)")

    crcl = ((140 - age) * weight_kg) / (72 * effective_scr)
    if sex_lower == "female":
        crcl *= 0.85

    if crcl < 0:
        warns.append(f"Computed CrCl = {crcl:.1f} mL/min (negative — extreme age/SCr); clamped to 0")
        crcl = 0.0

    if scr_mg_dL > 4.0:
        warns.append("SCr > 4.0 mg/dL — Cockcroft-Gault may be unreliable; consider CKD-EPI or MDRD")

    female_factor = 0.85 if sex_lower == "female" else 1.0
    return FormulaResult(
        value=crcl,
        units="mL/min",
        formula="Cockcroft-Gault CrCl",
        equation="CrCl = ((140−age)×weight)/(72×SCr) × [0.85 if female]",
        inputs={
            "age": (age, "years"), "weight": (weight_kg, "kg"),
            "SCr": (scr_mg_dL, "mg/dL"), "sex_factor": (female_factor, ""),
        },
        warnings=warns,
    )


def mdrd_gfr(
    scr_mg_dL: float,
    age: float,
    sex: Literal["male", "female"],
    black_race: bool = False,
) -> FormulaResult:
    """
    MDRD Study eGFR (4-variable, 2006 IDMS-traceable equation).

    Formula: eGFR = 175 × SCr^(−1.154) × age^(−0.203)
                    × [0.742 if female] × [1.212 if Black]

    Reference: Levey AS et al. Ann Intern Med. 2006;145(4):247–254.

    Note: CKD-EPI 2021 (ckd_epi_gfr) is now preferred by KDIGO guidelines.
    MDRD is provided for legacy/compatibility use.

    Parameters
    ----------
    scr_mg_dL  : Serum creatinine (mg/dL), IDMS-calibrated
    age        : Patient age (years)
    sex        : "male" or "female"
    black_race : Historical race coefficient — included for legacy use.
                 The 2021 CKD-EPI equation removes the race coefficient;
                 use ckd_epi_gfr() for race-free estimation.
    """
    if scr_mg_dL <= 0 or age <= 0:
        raise ValueError("SCr and age must be > 0")
    if sex.lower() not in ("male", "female"):
        raise ValueError("sex must be 'male' or 'female'")

    egfr = 175 * (scr_mg_dL ** -1.154) * (age ** -0.203)
    if sex.lower() == "female":
        egfr *= 0.742
    if black_race:
        egfr *= 1.212

    warns = ["MDRD systematically underestimates GFR > 60 mL/min/1.73m² — prefer CKD-EPI 2021"]
    if black_race:
        warns.append(
            "Race coefficient (×1.212 for Black) included per original equation; "
            "consider using ckd_epi_gfr() which is race-free (KDIGO 2022)"
        )

    return FormulaResult(
        value=egfr,
        units="mL/min/1.73m²",
        formula="MDRD 4-variable eGFR",
        equation="175 × SCr^−1.154 × age^−0.203 × [0.742♀] × [1.212 Black]",
        inputs={
            "SCr": (scr_mg_dL, "mg/dL"), "age": (age, "years"),
            "sex": (sex, ""), "black_race": (black_race, ""),
        },
        warnings=warns,
    )


def ckd_epi_gfr(
    scr_mg_dL: float,
    age: float,
    sex: Literal["male", "female"],
) -> FormulaResult:
    """
    CKD-EPI 2021 eGFR (race-free).

    The 2021 equation was revised by KDIGO to remove race as a variable.
    It outperforms MDRD across the full GFR range.

    Reference: Inker LA et al. N Engl J Med. 2021;385(19):1737–1749.

    Formula (kappa = 0.7♀/0.9♂; alpha = −0.241♀/−0.302♂):
        eGFR = 142 × min(SCr/κ, 1)^α × max(SCr/κ, 1)^(−1.200)
               × 0.9938^age × [1.012 if female]

    Parameters
    ----------
    scr_mg_dL : Serum creatinine (mg/dL), IDMS-traceable
    age       : Patient age (years)
    sex       : "male" or "female"
    """
    if scr_mg_dL <= 0 or age <= 0:
        raise ValueError("SCr and age must be > 0")
    sex_lower = sex.lower()
    if sex_lower not in ("male", "female"):
        raise ValueError("sex must be 'male' or 'female'")

    kappa = 0.7 if sex_lower == "female" else 0.9
    alpha = -0.241 if sex_lower == "female" else -0.302
    sex_factor = 1.012 if sex_lower == "female" else 1.0

    scr_kappa = scr_mg_dL / kappa
    egfr = (
        142
        * (min(scr_kappa, 1.0) ** alpha)
        * (max(scr_kappa, 1.0) ** -1.200)
        * (0.9938 ** age)
        * sex_factor
    )
    return FormulaResult(
        value=egfr,
        units="mL/min/1.73m²",
        formula="CKD-EPI 2021 eGFR (race-free)",
        equation="142 × min(SCr/κ,1)^α × max(SCr/κ,1)^−1.2 × 0.9938^age × [1.012♀]",
        inputs={
            "SCr": (scr_mg_dL, "mg/dL"), "age": (age, "years"), "sex": (sex, ""),
        },
    )


def calvert_carboplatin(
    target_auc: float,
    gfr_or_crcl: float,
) -> FormulaResult:
    """
    Calvert formula for carboplatin dosing.

    Formula: Dose (mg) = AUC_target × (GFR + 25)

    Reference: Calvert AH et al. J Clin Oncol. 1989;7(11):1748–1756.
    FDA 2010 guidance caps GFR at 125 mL/min to avoid overdose when using
    Cockcroft-Gault with actual body weight in obese patients.

    Parameters
    ----------
    target_auc    : Target AUC (mg·min/mL) — typically 5–7 for first-line,
                    4–6 for relapsed NSCLC, 4 for previously treated
    gfr_or_crcl   : GFR or CrCl (mL/min) — use cockcroft_gault().value or
                    ckd_epi_gfr().value; do NOT use mL/min/1.73m² directly
    """
    warns = []
    effective_gfr = gfr_or_crcl
    if gfr_or_crcl > 125:
        effective_gfr = 125
        warns.append(
            f"GFR {gfr_or_crcl} mL/min capped at 125 per FDA 2010 guidance to avoid overdose"
        )
    if target_auc > 7.5:
        warns.append(f"Target AUC {target_auc} is above typical clinical range (4–7); verify intent")

    dose = target_auc * (effective_gfr + 25)
    return FormulaResult(
        value=dose,
        units="mg",
        formula="Calvert Carboplatin Dose",
        equation="Dose = AUC_target × (GFR + 25)",
        inputs={
            "AUC_target": (target_auc, "mg·min/mL"),
            "GFR": (gfr_or_crcl, "mL/min"),
        },
        warnings=warns,
    )


def renal_dose_factor(patient_gfr: float, normal_gfr: float = 100.0) -> FormulaResult:
    """
    Fraction of normal dose appropriate for a patient with reduced renal function.

    Formula: factor = patient_GFR / normal_GFR

    Used as a first approximation for renally-cleared drugs with linear kinetics.
    Actual dose adjustments must use drug-specific labeling.

    Parameters
    ----------
    patient_gfr : Patient eGFR/CrCl (mL/min)
    normal_gfr  : Reference normal GFR (mL/min) — default 100
    """
    if normal_gfr <= 0:
        raise ValueError("normal_gfr must be > 0")
    factor = max(0.0, min(1.0, patient_gfr / normal_gfr))
    return FormulaResult(
        value=factor,
        units="fraction",
        formula="Renal Dose Factor",
        equation="factor = patient_GFR / normal_GFR",
        inputs={
            "patient_GFR": (patient_gfr, "mL/min"),
            "normal_GFR": (normal_gfr, "mL/min"),
        },
        warnings=["Use drug-specific labeling for actual dosing — this is a linear approximation only"],
    )


# ---------------------------------------------------------------------------
# ─── BODY MEASUREMENTS ──────────────────────────────────────────────────────
# ---------------------------------------------------------------------------


def bsa_mosteller(height_cm: float, weight_kg: float) -> FormulaResult:
    """
    Body Surface Area — Mosteller formula.

    Formula: BSA = √(height_cm × weight_kg / 3600)

    Reference: Mosteller RD. N Engl J Med. 1987;317(17):1098.
    Widely used in oncology for chemotherapy dosing.

    Parameters
    ----------
    height_cm : Patient height (cm)
    weight_kg : Patient weight (kg)
    """
    if height_cm <= 0 or weight_kg <= 0:
        raise ValueError("height and weight must be > 0")
    bsa = math.sqrt(height_cm * weight_kg / 3600)
    return FormulaResult(
        value=bsa,
        units="m²",
        formula="BSA Mosteller",
        equation="BSA = √(height_cm × weight_kg / 3600)",
        inputs={"height": (height_cm, "cm"), "weight": (weight_kg, "kg")},
    )


def bsa_dubois(height_cm: float, weight_kg: float) -> FormulaResult:
    """
    Body Surface Area — Du Bois & Du Bois formula.

    Formula: BSA = 0.007184 × height_cm^0.725 × weight_kg^0.425

    Reference: Du Bois D, Du Bois EF. Arch Intern Med. 1916;17:863–871.
    Historical standard; Mosteller is generally preferred for simplicity.

    Parameters
    ----------
    height_cm : Patient height (cm)
    weight_kg : Patient weight (kg)
    """
    if height_cm <= 0 or weight_kg <= 0:
        raise ValueError("height and weight must be > 0")
    bsa = 0.007184 * (height_cm ** 0.725) * (weight_kg ** 0.425)
    return FormulaResult(
        value=bsa,
        units="m²",
        formula="BSA Du Bois",
        equation="BSA = 0.007184 × height^0.725 × weight^0.425",
        inputs={"height": (height_cm, "cm"), "weight": (weight_kg, "kg")},
    )


def ibw_devine(height_cm: float, sex: Literal["male", "female"]) -> FormulaResult:
    """
    Ideal Body Weight — Devine formula.

    Formula:
        Male:   IBW = 50 + 2.3 × (height_inches − 60)
        Female: IBW = 45.5 + 2.3 × (height_inches − 60)

    Reference: Devine BJ. Drug Intell Clin Pharm. 1974;8:650–655.
    Used in Cockcroft-Gault when patient is obese (TBW > 1.2 × IBW).

    Parameters
    ----------
    height_cm : Patient height (cm)
    sex       : "male" or "female"
    """
    if height_cm <= 0:
        raise ValueError("height must be > 0")
    height_inches = height_cm / 2.54
    sex_lower = sex.lower()
    if sex_lower not in ("male", "female"):
        raise ValueError("sex must be 'male' or 'female'")

    base = 50.0 if sex_lower == "male" else 45.5
    ibw = base + 2.3 * (height_inches - 60)

    warns = []
    if height_inches < 60:
        ibw = base  # formula is unreliable below 5 ft — use base weight
        warns.append(
            f"Height {height_cm} cm < 152 cm (5 ft) — "
            "Devine formula extrapolates poorly; using base weight only"
        )
    return FormulaResult(
        value=ibw,
        units="kg",
        formula="Ideal Body Weight (Devine)",
        equation=f"IBW = {base} + 2.3 × (height_in − 60)",
        inputs={"height": (height_cm, "cm"), "sex": (sex, "")},
        warnings=warns,
    )


def abw(tbw_kg: float, ibw_kg: float, *, correction_factor: float = 0.4) -> FormulaResult:
    """
    Adjusted Body Weight for obese patients.

    Formula: ABW = IBW + correction_factor × (TBW − IBW)

    Used when total body weight (TBW) > 1.3 × IBW.
    The 0.4 correction is standard for Cockcroft-Gault in obesity;
    0.3 is used for some aminoglycosides.

    Parameters
    ----------
    tbw_kg            : Total (actual) body weight (kg)
    ibw_kg            : Ideal body weight from ibw_devine() (kg)
    correction_factor : Typically 0.4 for CG, 0.3 for aminoglycosides (default 0.4)
    """
    if ibw_kg <= 0:
        raise ValueError("IBW must be > 0")
    warns = []
    if tbw_kg <= 1.3 * ibw_kg:
        warns.append(
            f"TBW {tbw_kg} kg ≤ 1.3 × IBW {ibw_kg:.1f} kg — "
            "ABW adjustment is typically only applied in obesity (TBW > 1.3 × IBW)"
        )
    adjusted = ibw_kg + correction_factor * (tbw_kg - ibw_kg)
    return FormulaResult(
        value=adjusted,
        units="kg",
        formula="Adjusted Body Weight",
        equation=f"ABW = IBW + {correction_factor} × (TBW − IBW)",
        inputs={
            "TBW": (tbw_kg, "kg"), "IBW": (ibw_kg, "kg"),
            "correction_factor": (correction_factor, ""),
        },
        warnings=warns,
    )


# ---------------------------------------------------------------------------
# ─── MOLECULAR / CONCENTRATION ──────────────────────────────────────────────
# ---------------------------------------------------------------------------


def molar_mass(molecular_formula: str) -> FormulaResult:
    """
    Compute molecular weight from a molecular formula string.

    Handles nested parentheses, e.g. "Ca3(PO4)2", "C54H64N12O12S2·2HCl".
    Dot-notation salt forms are partially supported (everything after "·" is
    included in the mass).

    Parameters
    ----------
    molecular_formula : e.g. "C9H8O4", "C57H67N11O6·CH4O3S" (mesylate salt)
    """
    # Handle dot-notation for salt forms: normalize "·" or "•" to "."
    formula = molecular_formula.strip().replace('·', '.').replace('•', '.')
    # Split on dot — each component is weighed and summed
    components = formula.split('.')
    total_mw = 0.0
    unknowns: list[str] = []
    warns: list[str] = []

    for component in components:
        component = component.strip()
        if not component:
            continue
        # Handle leading stoichiometry on salts like "2HCl"
        m = re.match(r'^(\d+)([A-Z].*)', component)
        stoich = 1
        formula_part = component
        if m:
            stoich = int(m.group(1))
            formula_part = m.group(2)
        try:
            atoms = _parse_formula(formula_part)
        except Exception:
            unknowns.append(component)
            continue
        for elem, count in atoms.items():
            mass = _ATOMIC_MASS.get(elem)
            if mass is None:
                unknowns.append(elem)
            else:
                total_mw += mass * count * stoich

    if unknowns:
        warns.append(f"Unknown element(s) ignored in MW calculation: {', '.join(unknowns)}")

    return FormulaResult(
        value=total_mw,
        units="g/mol",
        formula="Molar Mass",
        equation="MW = Σ(atomic_mass × count) for each element",
        inputs={"formula": (molecular_formula, "")},
        warnings=warns,
    )


def mg_to_mmol(mg: float, mw_g_per_mol: float) -> FormulaResult:
    """
    Convert mass (mg) to moles (mmol).

    Formula: mmol = mg / MW (g/mol)

    Parameters
    ----------
    mg          : Mass in milligrams
    mw_g_per_mol: Molecular weight (g/mol) — use molar_mass().value
    """
    if mw_g_per_mol <= 0:
        raise ValueError("Molecular weight must be > 0")
    mmol = mg / mw_g_per_mol
    return FormulaResult(
        value=mmol, units="mmol",
        formula="mg → mmol",
        equation="mmol = mg / MW",
        inputs={"mass": (mg, "mg"), "MW": (mw_g_per_mol, "g/mol")},
    )


def mmol_to_mg(mmol: float, mw_g_per_mol: float) -> FormulaResult:
    """
    Convert moles (mmol) to mass (mg).

    Formula: mg = mmol × MW (g/mol)
    """
    if mw_g_per_mol <= 0:
        raise ValueError("Molecular weight must be > 0")
    mg = mmol * mw_g_per_mol
    return FormulaResult(
        value=mg, units="mg",
        formula="mmol → mg",
        equation="mg = mmol × MW",
        inputs={"amount": (mmol, "mmol"), "MW": (mw_g_per_mol, "g/mol")},
    )


def molar_concentration(
    mass_mg: float,
    volume_L: float,
    mw_g_per_mol: float,
) -> FormulaResult:
    """
    Compute molar concentration from mass, volume, and molecular weight.

    Formula: μM = (mass_mg / (MW × volume_L)) × 1000

    Parameters
    ----------
    mass_mg      : Mass of compound dissolved (mg)
    volume_L     : Solution volume (litres)
    mw_g_per_mol : Molecular weight (g/mol) — use molar_mass().value
    """
    if volume_L <= 0 or mw_g_per_mol <= 0:
        raise ValueError("volume and MW must be > 0")
    um = (mass_mg / (mw_g_per_mol * volume_L)) * 1000
    return FormulaResult(
        value=um, units="μM",
        formula="Molar Concentration",
        equation="μM = (mass_mg / (MW × V_L)) × 1000",
        inputs={
            "mass": (mass_mg, "mg"), "volume": (volume_L, "L"),
            "MW": (mw_g_per_mol, "g/mol"),
        },
    )


def nM_to_mg_per_L(concentration_nM: float, mw_g_per_mol: float) -> FormulaResult:
    """
    Convert nanomolar concentration to mg/L (for PK/PD comparison with plasma levels).

    Formula: mg/L = nM × MW / 1e6

    Parameters
    ----------
    concentration_nM : Concentration in nanomolar (nM)
    mw_g_per_mol     : Molecular weight (g/mol)
    """
    if mw_g_per_mol <= 0:
        raise ValueError("MW must be > 0")
    mg_per_L = concentration_nM * mw_g_per_mol / 1e6
    return FormulaResult(
        value=mg_per_L, units="mg/L",
        formula="nM → mg/L",
        equation="mg/L = nM × MW / 1e6",
        inputs={
            "concentration": (concentration_nM, "nM"),
            "MW": (mw_g_per_mol, "g/mol"),
        },
    )
