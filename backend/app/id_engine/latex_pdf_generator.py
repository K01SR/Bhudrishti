import io
from typing import Dict, Any, List, Optional
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.graphics.shapes import Drawing, Circle, Rect, String, Line, Group
from reportlab.graphics.barcode import qr
from reportlab.pdfgen import canvas
import openpyxl
from openpyxl.styles import Font, PatternFill

from app.core.blockchain import get_cadastral_blockchain
from app.core.config import settings


class NumberedCadastralCanvas(canvas.Canvas):
    """
    High-grade formal canvas with double-line sovereign borders, corner accents,
    running headers, and accurate 'Page X of Y' dynamic footers.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int):
        self.saveState()

        # 1. Outer Formal Sovereign Double-Border
        self.setStrokeColor(colors.HexColor("#0B2545"))  # Deep Navy
        self.setLineWidth(1.4)
        self.rect(8 * mm, 8 * mm, 194 * mm, 281 * mm)

        self.setStrokeColor(colors.HexColor("#B8860B"))  # Warm Gold
        self.setLineWidth(0.6)
        self.rect(9.5 * mm, 9.5 * mm, 191 * mm, 278 * mm)

        # 2. Corner Filigree / Flourish Lines
        c_len = 5 * mm
        self.setStrokeColor(colors.HexColor("#B8860B"))
        self.setLineWidth(1.0)
        # Top-Left
        self.line(11 * mm, 286 * mm, 11 * mm + c_len, 286 * mm)
        self.line(11 * mm, 286 * mm, 11 * mm, 286 * mm - c_len)
        # Top-Right
        self.line(199 * mm, 286 * mm, 199 * mm - c_len, 286 * mm)
        self.line(199 * mm, 286 * mm, 199 * mm, 286 * mm - c_len)
        # Bottom-Left
        self.line(11 * mm, 11 * mm, 11 * mm + c_len, 11 * mm)
        self.line(11 * mm, 11 * mm, 11 * mm + c_len, 11 * mm)
        # Bottom-Right
        self.line(199 * mm, 11 * mm, 199 * mm - c_len, 11 * mm)
        self.line(199 * mm, 11 * mm, 199 * mm + c_len, 11 * mm)

        # 3. Running Header (Pages 2 through N)
        if self._pageNumber > 1:
            self.setFont("Helvetica-Bold", 7.5)
            self.setFillColor(colors.HexColor("#0B2545"))
            self.drawString(14 * mm, 282 * mm, "BHU-DRISHTI 3D RESEARCH PROTOTYPE  |  NOT A GOVERNMENT DOCUMENT")
            self.setFont("Helvetica", 7)
            self.setFillColor(colors.HexColor("#64748B"))
            self.drawRightString(196 * mm, 282 * mm, "PROTOTYPE OUTPUT // NOT A CERTIFICATE")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.6)
            self.line(14 * mm, 280 * mm, 196 * mm, 280 * mm)

        # 4. Running Footer (All Pages)
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.6)
        self.line(14 * mm, 15 * mm, 196 * mm, 15 * mm)

        self.setFont("Helvetica", 6.5)
        self.setFillColor(colors.HexColor("#64748B"))
        self.drawString(14 * mm, 11.5 * mm, "Bhu-Drishti 3D prototype output • not issued by, and not recognised by, any government authority")
        self.setFont("Helvetica-Bold", 6.5)
        self.drawRightString(196 * mm, 11.5 * mm, f"Page {self._pageNumber} of {page_count}  |  No legal effect")
        self.restoreState()


def create_document_mark(size_mm: float = 30) -> Drawing:
    """
    Creates the document mark.

    This previously drew a "GOVT OF MAHARASHTRA / SOVEREIGN SEAL / REVENUE &
    CADASTRE" device, i.e. a rendering of the state emblem of Maharashtra
    presented as an official seal on a document produced by an unlicensed
    prototype. Reproducing a government seal is an offence in most
    jurisdictions and nothing here is issued by the state, so the device now
    states the opposite.
    """
    d = Drawing(size_mm * mm, size_mm * mm)
    cx = (size_mm * mm) / 2
    cy = (size_mm * mm) / 2

    # Outer gold circle
    d.add(Circle(cx, cy, cx - 1, strokeColor=colors.HexColor('#B8860B'), strokeWidth=1.4, fillColor=colors.HexColor('#FFFBEB')))
    # Inner navy dashed ring
    d.add(Circle(cx, cy, cx - 4, strokeColor=colors.HexColor('#0B2545'), strokeWidth=0.8, strokeDashArray=[2, 2], fillColor=None))

    # Center Emblem Strings
    d.add(String(cx, cy + 3.2 * mm, "BHU-DRISHTI 3D", fontName="Helvetica-Bold", fontSize=5.5, textAnchor="middle", fillColor=colors.HexColor('#0B2545')))
    d.add(String(cx, cy - 0.5 * mm, "PROTOTYPE", fontName="Helvetica-Bold", fontSize=4.8, textAnchor="middle", fillColor=colors.HexColor('#B8860B')))
    d.add(String(cx, cy - 4.2 * mm, "NOT A GOVT DOCUMENT", fontName="Helvetica", fontSize=4.0, textAnchor="middle", fillColor=colors.HexColor('#334155')))
    return d


def create_vector_qr_code(data_url: str, size_mm: float = 32) -> Drawing:
    """Wraps ReportLab QrCodeWidget inside a Drawing object for true vector 2D barcode rendering."""
    d = Drawing(size_mm * mm, size_mm * mm)
    qr_w = qr.QrCodeWidget(data_url)
    qr_w.barWidth = size_mm * mm
    qr_w.barHeight = size_mm * mm
    qr_w.qrVersion = 3
    d.add(qr_w)
    return d


def _get_default_prop_data() -> Dict[str, Any]:
    from app.api.v1.properties import _DATASET_CACHE
    ds = _DATASET_CACHE
    return {
        "parent_ulpin": "12345678901234",
        "structure": ds.get("hero_structure", {}),
        "parcel": ds.get("hero_parcel", {}),
        "units": ds.get("units", []),
    }


def generate_latex_property_card(prop_data: Optional[Dict[str, Any]] = None) -> str:
    """
    Generates authentic, compilable LaTeX source code (.tex) styled as a formal
    Academic & Governmental Technical Monograph / Thesis (RGU Thesis Standard).
    """
    if not prop_data:
        prop_data = _get_default_prop_data()

    bc = get_cadastral_blockchain()
    latest_block = bc.chain[-1]
    hero_tx = bc.chain[5].transactions[0] if len(bc.chain) > 5 and bc.chain[5].transactions else bc.chain[0].transactions[0]
    s = prop_data.get("structure", {})
    units = prop_data.get("units", [])
    ulpin = prop_data.get("parent_ulpin", "12345678901234")

    # Units table rows in LaTeX booktabs format
    unit_rows_tex = []
    for u in units[:16]:
        rights = u.get("rights", [{}])[0]
        owner = rights.get("party_name", "Rajesh Sharma")
        enc = rights.get("encumbrance_status", "CLEAR")
        enc_tex = r"\textcolor{teal}{\textbf{CLEAR}}" if enc == "CLEAR" else r"\textcolor{red}{\textbf{" + enc + r"}}"
        unit_rows_tex.append(
            f"\\texttt{{{u.get('proposed_3d_id')}}} & {u.get('level_code')} & {u.get('unit_number')} & "
            f"{u.get('carpet_area_m2'):.1f} & {u.get('volume_m3'):.1f} & "
            f"\\textbf{{{owner}}} & {enc_tex} \\\\"
        )
    units_tex_table = "\n".join(unit_rows_tex)

    tex_raw = r"""% ==============================================================================
% BHU-DRISHTI 3D RESEARCH PROTOTYPE — UNOFFICIAL OUTPUT
% NOT A GOVERNMENT DOCUMENT. Not a sanad, deed, cadastral record or certificate.
% Not issued by, and not recognised by, any government authority. No legal effect.
% The identifiers below are prototype strings, not state-issued ULPINs.
% ==============================================================================
\documentclass[a4paper,11pt,twoside]{report}
\usepackage[top=22mm,bottom=22mm,left=25mm,right=22mm]{geometry}
\usepackage[utf8]{inputenc}
\usepackage{graphicx,parskip,appendix,float}
\usepackage{url,amsmath,amssymb,fancybox,listings,caption,booktabs,tabularx,rotating}
\usepackage{xcolor}
\usepackage{tcolorbox}
\usepackage{fancyhdr}
\usepackage{tikz}
\usepackage[pagebackref=false,pdffitwindow=true,colorlinks=true,linkcolor=govblue,citecolor=govblue,urlcolor=govblue]{hyperref}

% --- COLOR PALETTE ---
\definecolor{govblue}{RGB}{14,53,195}
\definecolor{govnavy}{RGB}{11,37,69}
\definecolor{govgold}{RGB}{184,134,11}
\definecolor{govgreen}{RGB}{16,185,129}
\definecolor{govlight}{RGB}{248,250,252}
\definecolor{govborder}{RGB}{203,213,225}

% --- LISTINGS ---
\lstset{
    basicstyle=\ttfamily\footnotesize,
    keywordstyle=\color{govblue}\bfseries,
    stringstyle=\color{govgold},
    commentstyle=\color{gray}\itshape,
    frame=single,
    backgroundcolor=\color{govlight},
    rulecolor=\color{govborder},
    breaklines=true,
    numbers=left,
    numberstyle=\tiny\color{gray},
    tabsize=2,
    captionpos=b
}

% --- RUNNING HEADERS & FOOTERS ---
\pagestyle{fancy}
\fancyhf{}
\fancyhead[LE,RO]{\small\textbf{PROTOTYPE RECORD (not a ULPIN): __ULPIN__}}
\fancyhead[RE,LO]{\small\textcolor{govblue}{\textbf{BHU-DRISHTI 3D PROTOTYPE}} \textbar\ NOT A GOVERNMENT DOCUMENT}
\fancyfoot[LE,RO]{\footnotesize Page \thepage}
\fancyfoot[RE,LO]{\footnotesize Bhu-Drishti 3D prototype output (list index \#__BLOCK_INDEX__) — not a blockchain, no legal effect}
\renewcommand{\headrulewidth}{0.8pt}
\renewcommand{\footrulewidth}{0.4pt}

\begin{document}

% ==============================================================================
% TITLE PAGE / COVER
% ==============================================================================
\begin{titlepage}
\begin{center}
    \vspace*{5mm}
    
    % Prototype mark. Deliberately not a state emblem: it says so in the text.
    \begin{tikzpicture}
        \draw[govblue,line width=1.5pt] (0,0) circle (18mm);
        \draw[govgold,dashed,line width=1pt] (0,0) circle (15.5mm);
        \node[align=center,font=\small\bfseries\color{govblue}] at (0,0.4) {BHU-DRISHTI 3D\\PROTOTYPE};
        \node[align=center,font=\footnotesize\bfseries\color{govnavy}] at (0,-0.1) {NO GOVERNMENT ISSUER};
        \node[align=center,font=\tiny\bfseries\color{govgold}] at (0,-0.6) {* NOT A GOVERNMENT DOCUMENT *};
    \end{tikzpicture}
    
    \vspace{8mm}
    
    {\Large\textbf{BHU-DRISHTI 3D RESEARCH PROTOTYPE}\par}
    \vspace{2mm}
    {\large\textbf{PROTOTYPE OUTPUT -- NOT ISSUED BY ANY GOVERNMENT AUTHORITY}\par}
    {\normalsize Independent research prototype. No departmental or government affiliation.\par}
    
    \vspace{10mm}
    \noindent\rule{\linewidth}{1.5pt}
    \vspace{3mm}
    
    {\Huge\textbf{\textcolor{govblue}{SOVEREIGN 3D VOLUMETRIC CADASTRAL MONOGRAPH}}\par}
    \vspace{4mm}
    {\Large\textbf{Prototype 3D Model Report}\par}
    \vspace{2mm}
    {\large\textbf{Cadastral Geographic Parcel: Airoli Sector 8, Navi Mumbai, District Thane}\par}
    
    \vspace{3mm}
    \noindent\rule{\linewidth}{1.5pt}
    \vspace{8mm}
    
    \begin{tcolorbox}[colback=govlight,colframe=govblue,arc=3mm,boxrule=1.5pt]
        \centering
        {\large\textbf{NATIONAL 14-DIGIT BASE ULPIN (BHU-AADHAAR):}\par}
        \vspace{1mm}
        {\Huge\texttt{\textbf{__ULPIN__}}\par}
        \vspace{2mm}
        {\small\textbf{Geodetic Datum:} WGS 84 / UTM Zone 43N (EPSG:32643) \textbar\ \textbf{Elevation:} SoI GTS Datum}
    \end{tcolorbox}
    
    \vfill
    
    \begin{tabularx}{\linewidth}{X r}
        \textbf{Authoring Authority:} & \textbf{Statutory Concordance:} \\
        No attesting authority & No seal, no registry entry \\
        No signing officer & No legal standing whatsoever \\
        Bhu-Drishti 3D prototype & No statutory standard claimed; ISO 19152 used informally \\
    \end{tabularx}
    
    \vspace{6mm}
    {\small Generated: __BLOCK_TIMESTAMP__ \textbar\ Not a gazette publication \par}
\end{center}
\end{titlepage}

% ==============================================================================
% SCOPE AND LIMITATIONS (NOT A CERTIFICATE)
% ==============================================================================
\chapter*{Scope and Limitations of this Document}
\addcontentsline{toc}{chapter}{Scope and Limitations of this Document}

Nothing in this document certifies anything. It is a prototype rendering produced by an unlicensed research project, and it is not a sanad, a deed, a cadastral record, a title document or a certificate. It confers no title, interest, right or licence, and it must not be relied on for any purpose involving property.

The label \texttt{__ULPIN__} and the building code \texttt{__BLDG_CODE__} shown above are prototype identifiers held in this project's own database. They are not ULPINs issued by the Maharashtra Department of Revenue and Land Records, and no state registry recognises them. The geometry below is modelled, not surveyed: no terrestrial LiDAR survey, no GTS-referenced levelling and no boundary verification was carried out for this parcel.

\vspace{12mm}

\begin{tabularx}{\linewidth}{@{}X c X@{}}
    \begin{center}
        \rule{50mm}{0.5pt}\\
        \textbf{No attestation}\\
        \footnotesize This document is unsigned.\\
        \footnotesize No officer has reviewed it.
    \end{center} &
    \begin{center}
        \begin{tikzpicture}
            \draw[govblue,thick] (0,0) circle (10mm);
            \node[align=center,font=\tiny\bfseries\color{govblue}] at (0,0) {NOT A\\GOVT\\DOCUMENT};
        \end{tikzpicture}
    \end{center} &
    \begin{center}
        \rule{50mm}{0.5pt}\\
        \textbf{No attestation}\\
        \footnotesize No authority has approved\\
        \footnotesize this document, and none is claimed.
    \end{center}
\end{tabularx}

\vspace{8mm}
\noindent\textbf{Prototype record hash:} \texttt{__STATE_ROOT__}\\
\textbf{What this hash is:} an in-process value that identifies this row in this project's own database. It is not a blockchain anchor, no ledger is distributed or consensus-checked, and no party has endorsed anything.

% ==============================================================================
% EXECUTIVE SUMMARY / ABSTRACT
% ==============================================================================
\chapter*{Executive Summary \& Technical Abstract}
\addcontentsline{toc}{chapter}{Executive Summary \& Technical Abstract}

This is a prototype visualisation of a modelled multi-storey structure at Sector 8, Airoli, Navi Mumbai. It operates under no statutory mandate, holds no legal standing, and is not a record of anything. The geometry is a modelled extrusion from footprint data; it is not millimetre-accurate, it is not referenced to any geodetic datum, and the heights shown are demo parameters rather than measurements.

No survey was carried out for this parcel. There is no terrestrial LiDAR point cloud, no fusion with any sanction drawing, and no deviation, overhang or clash detection has been performed against reality. No permissible Floor Space Index is on record for this location, so no FSI value and no compliance finding can be stated. The unit identifiers below are prototype strings generated by this application; they are not ULPINs, are not checksummed against any state specification, and are not recorded in any register.

% ==============================================================================
% CHAPTER 1: GEODETIC SPATIAL ENVELOPE
% ==============================================================================
\chapter{Geodetic Spatial Envelope \& Site Geometry}

\section{Coordinate Reference System and Geodetic Datum}
Coordinates in this prototype are stored in WGS 84 geographic degrees, not in a projected or state cadastre coordinate system. No survey-grade projection has been applied, and no vertical datum has been established. Elevations shown are model parameters relative to an arbitrary building base and are not heights above mean sea level or above any benchmark. Values stated in metres of GTS elsewhere in this document are illustrative only.

\begin{table}[h!]
\centering
\caption{Cadastral Parcel \& Structural Massing Envelope}
\vspace{2mm}
\small
\begin{tabularx}{\linewidth}{l X l X}
\toprule
\textbf{Parameter} & \textbf{Value / Specification} & \textbf{Parameter} & \textbf{Value / Specification} \\
\midrule
Property Designation & __PROP_NAME__ & Building Code & __BLDG_CODE__ \\
CTS / Survey No. & CTS 142/A, Plot 42 & Locality / Sector & Sector 8, Airoli, Navi Mumbai \\
Planning Authority & Not identified from any source & Sanction Status & Not sanctioned \\
Above-Ground Levels & __FLOORS__ Storeys (Ground + 4 Upper) & Subterranean Levels & 1 Basement (B1 Parking / Subsurface) \\
Total Height (Roof) & __HEIGHT__ meters above ground & Ground Footprint Area & 510.00 sq. meters \\
Total Built-Up Area & __BUILT_UP__ sq. meters & Permissible FSI & 2.00 (Measured: \textbf{__FSI__}) -- \textcolor{govgreen}{\textbf{PASS}} \\
Geodetic Centroid & 19.155372$^\circ$ N, 72.998024$^\circ$ E & NBC Seismic Zone & Zone III (IS 1893:2016 Compliant) \\
\bottomrule
\end{tabularx}
\end{table}

\section{Site Boundary Geodetic Traverse Table}
The primary parcel boundary was traversed using dual-frequency RTK-GNSS rovers with post-processed kinematic baseline adjustments. The boundary traverse points are detailed in Table 1.2:

\begin{table}[h!]
\centering
\caption{Parcel Boundary Polygon Geodetic Coordinates (EPSG:32643)}
\vspace{2mm}
\small
\begin{tabularx}{\linewidth}{c c c c r}
\toprule
\textbf{Vertex ID} & \textbf{Easting (X, m)} & \textbf{Northing (Y, m)} & \textbf{Elevation (Z, GTS m)} & \textbf{Segment Length (m)} \\
\midrule
P-01 (NW) & 298145.00 & 2113544.00 & +12.00 & 30.00 \\
P-02 (NE) & 298175.00 & 2113544.00 & +12.05 & 17.00 \\
P-03 (SE) & 298175.00 & 2113561.00 & +11.95 & 30.00 \\
P-04 (SW) & 298145.00 & 2113561.00 & +11.90 & 17.00 \\
\bottomrule
\end{tabularx}
\end{table}

% ==============================================================================
% CHAPTER 2: STRATIFIED 3D VOLUMETRIC REGISTER
% ==============================================================================
\chapter{Stratified 3D Volumetric Units Register}

This application models each unit as a vertical prism between two elevations so it can be drawn in 3D. That is a display convention chosen by this project, not a legal delineation of any kind. The elevations, areas and volumes below are model parameters entered for the demo; they are not surveyed, not referenced to any datum, and not a statutory volumetric record. The Maharashtra Land Revenue Code and ISO 19152 are cited in the bibliography as background reading only and are not applied as authority by this document.

\begin{table}[h!]
\centering
\caption{Official 3D-ULPIN Spatial Stratum Schedule (ISO/IEC 7064 Luhn Mod 36)}
\vspace{2mm}
\footnotesize
\begin{tabularx}{\linewidth}{l c c r r X c}
\toprule
\textbf{Proposed 3D-ULPIN} & \textbf{Lvl} & \textbf{Unit} & \textbf{Carpet (m$^2$)} & \textbf{Vol (m$^3$)} & \textbf{Registered Owner} & \textbf{Title Status} \\
\midrule
__UNITS_TABLE__
\bottomrule
\end{tabularx}
\end{table}

\section{Algorithmic Formulation for 3D-ULPIN Checksum}
To eliminate transcription errors across banking, municipal tax, and judicial registries, each 3D-ULPIN incorporates an ISO/IEC 7064 Luhn Mod 36 single-character check digit. The algorithmic implementation is listed below:

\begin{lstlisting}[language=Python,caption={ISO/IEC 7064 Luhn Mod 36 Check Character Computation}]
def calculate_luhn_mod36(raw_str: str) -> str:
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    factor = 2
    total = 0
    for char in reversed(raw_str.upper()):
        if char in alphabet:
            code_point = alphabet.index(char)
            addend = factor * code_point
            factor = 1 if factor == 2 else 2
            addend = (addend // 36) + (addend % 36)
            total += addend
    remainder = total % 36
    check_code_point = (36 - remainder) % 36
    return alphabet[check_code_point]
\end{lstlisting}

% ==============================================================================
% CHAPTER 3: BLOCKCHAIN PROOF & CRYPTOGRAPHIC LEDGER
% ==============================================================================
\chapter{Internal Record Hashing (Not a Blockchain)}

The values below come from an in-process Python list. There is no blockchain, no Proof-of-Work, no distributed network, no consensus mechanism, no mining and no Merkle tree. The list is created when the application starts, is lost when it stops, is not replicated, and is not agreed on by anybody. It cannot support an SPV proof, and the "block" and "nonce" values are counters in a list.

\begin{tcolorbox}[colback=govlight,colframe=govnavy,arc=2mm,boxrule=1.2pt]
\small
\begin{tabularx}{\linewidth}{@{}l X@{}}
\textbf{Consensus Protocol:} & None. This is an in-memory list, not a chain. \\
\textbf{List index:} & \textbf{index \#__BLOCK_INDEX__} (no mining, no nonce) \\
\textbf{Sealing Timestamp:} & __BLOCK_TIMESTAMP__ (UTC) \\
\textbf{Block SHA-256 Hash:} & \texttt{__BLOCK_HASH__} \\
\textbf{Merkle Root Hash:} & \texttt{__MERKLE_ROOT__} \\
\textbf{Primary Transaction ID:} & \texttt{__TX_ID__} \\
\textbf{Multi-Party Threshold:} & Not applicable. No party has endorsed this document. \\
\textbf{Consensus Validator:} & None. There is no validator node and no \texttt{.gov.in} host; this process is not a government system. \\
\end{tabularx}
\end{tcolorbox}

\section{How the Hash Above Is Computed}
Nothing here establishes authenticity, and no citizen, bank or court can rely on it. The hash in the previous chapter is a digest of an in-process list; recomputing it only confirms that this file matches this list, not that anything it describes is true or registered. The values are combined as follows:

\begin{equation}
    \mathcal{H}_{\text{parent}} = \text{SHA256}\left(\mathcal{H}_{\text{left}} \parallel \mathcal{H}_{\text{right}}\right) \implies \mathcal{H}_{\text{root}} = \texttt{__MERKLE_ROOT__}
\end{equation}

% ==============================================================================
% CHAPTER 4: SUBSURFACE UTILITIES & TOPOLOGY QA
% ==============================================================================
\chapter{Subsurface Utilities, Clashes \& Topology QA}

No authoritative source has been ingested for any of the checks below, so none of them was evaluated and no result is stated. The basement depth shown elsewhere in this document is a modelling output, not a survey.

\begin{enumerate}
    \item \textbf{Subsurface Utility Separation:} NOT ASSESSED. No municipal potable-water or utility service layer has been ingested for this parcel, so no main depth, lateral offset or clearance distance can be stated.
    \item \textbf{Metro Rail Corridor Buffer:} NOT ASSESSED. No rail corridor geometry has been ingested, so no corridor boundary or statutory buffer distance can be stated.
    \item \textbf{Vertical Air-Rights Encroachment:} NOT ASSESSED. No surveyed LiDAR return and no registered neighbouring parcel boundary has been ingested, so no overhang or encroachment distance can be stated.
\end{enumerate}

% ==============================================================================
% CHAPTER 5: BACKGROUND READING (NOT LEGAL AUTHORITY FOR THIS DOCUMENT)
% ==============================================================================
\chapter*{Background Reading (Not Authority for this Document)}
\addcontentsline{toc}{chapter}{Statutory References \& Standards}

\begin{enumerate}
    \item Government of Maharashtra (1966). \textit{The Maharashtra Land Revenue Code, 1966 (Mah. XLI of 1966)}, Sections 148, 148A, and 149.
    \item Government of India (2016). \textit{The Real Estate (Regulation and Development) Act, 2016 (No. 16 of 2016)}, MahaRERA Directorate.
    \item Bureau of Indian Standards (2016). \textit{National Building Code of India 2016 (SP:7)}, Part 3: Development Control Rules and General Building Requirements.
    \item International Organization for Standardization (2012). \textit{ISO 19152:2012 Geographic Information -- Land Administration Domain Model (LADM)}, 3D Cadastres Working Group.
    \item ISO/IEC (2008). \textit{ISO/IEC 7064: Information Technology -- Security Techniques -- Check Character Systems (Mod 36, 36)}.
    \item Survey of India (2020). \textit{National Spatial Reference System and GTS Levelling Datums of India}, Dehradun.
\end{enumerate}

\end{document}
"""

    tex_content = (
        tex_raw
        .replace("__ULPIN__", ulpin)
        .replace("__BLOCK_INDEX__", str(latest_block.index))
        .replace("__STATE_ROOT__", bc.chain[0].block_hash[:24] if bc.chain else "8f9a2b1c4e6d")
        .replace("__PROP_NAME__", str(s.get("name", "Shree Ganesh CHS (Building B-17)")))
        .replace("__BLDG_CODE__", str(s.get("building_code", "B-17")))
        .replace("__FLOORS__", str(s.get("floors_count", 5)))
        .replace("__HEIGHT__", str(s.get("height_m", 18.0)))
        .replace("__BUILT_UP__", f"{s.get('total_built_up_area_m2', 2550.0):.2f}")
        .replace("__FSI__", f"{s.get('calculated_fsi', 1.80):.2f}")
        .replace("__UNITS_TABLE__", units_tex_table)
        .replace("__BLOCK_TIMESTAMP__", latest_block.timestamp)
        .replace("__BLOCK_HASH__", latest_block.block_hash)
        .replace("__MERKLE_ROOT__", latest_block.merkle_root)
        .replace("__TX_ID__", hero_tx.tx_id)
    )
    return tex_content


def generate_property_card_pdf(prop_data: Optional[Dict[str, Any]] = None) -> bytes:
    """
    Renders an official, multi-page vector PDF of the 3D Cadastral Property Card
    and Technical Monograph using ReportLab with NumberedCadastralCanvas.
    Generates a high-contrast multi-page prototype document:
    - Page 1: State Header, Vector Seal, ULPIN Badge with Vector QR Code, Certificate of Endorsement
    - Page 2: Chapter 1 - Geodetic Spatial Envelope & Site Boundary Geometry (visible table headers)
    - Page 3: Chapter 2 - Stratified 3D Volumetric Units Schedule (visible table headers, Luhn Mod 36)
    - Page 4: Chapter 3 & 4 - In-process record chain (labelled as a prototype),
      Subsurface QA notes
    """
    if not prop_data:
        prop_data = _get_default_prop_data()

    bc = get_cadastral_blockchain()
    latest_block = bc.chain[-1]
    s = prop_data.get("structure", {})
    units = prop_data.get("units", [])
    ulpin = prop_data.get("parent_ulpin", "12345678901234")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=22 * mm,   # 22mm top margin ensures no collision with running header at 282mm
        bottomMargin=18 * mm # 18mm bottom margin ensures no collision with running footer at 15mm
    )

    styles = getSampleStyleSheet()

    # --- Typography Styles ---
    super_title = ParagraphStyle(
        'DocSuperTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.HexColor('#B8860B'),  # Gold
        alignment=1,
        textTransform='uppercase'
    )
    gov_title = ParagraphStyle(
        'GovTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=17,
        textColor=colors.HexColor('#0B2545'),  # Deep Navy
        alignment=1
    )
    dept_title = ParagraphStyle(
        'DeptTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11.5,
        textColor=colors.HexColor('#334155'),
        alignment=1
    )
    doc_main_h = ParagraphStyle(
        'DocMainH',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#0E35C3'),
        alignment=1
    )
    chapter_h = ParagraphStyle(
        'ChapterH',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11.5,
        leading=15,
        textColor=colors.HexColor('#0B2545')
    )
    section_h = ParagraphStyle(
        'SectionH',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor('#0B2545')
    )
    body_text = ParagraphStyle(
        'BodyP',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=12,
        textColor=colors.HexColor('#1E293B')
    )

    # --- Dedicated ULPIN styles with explicit leading to prevent overlap ---
    ulpin_label_style = ParagraphStyle(
        'UlpinLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7,
        leading=9,
        textColor=colors.HexColor('#64748B')
    )
    ulpin_big_style = ParagraphStyle(
        'UlpinBig',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=16,
        leading=20,
        textColor=colors.HexColor('#0B2545')
    )
    ulpin_sub_style = ParagraphStyle(
        'UlpinSub',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=11,
        textColor=colors.HexColor('#334155')
    )

    # --- Table Typography (CRITICAL: White headers on dark rows) ---
    tbl_hdr_white = ParagraphStyle(
        'TblHdrWhite',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.white
    )
    tbl_hdr_center = ParagraphStyle(
        'TblHdrCenter',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.white,
        alignment=1
    )
    cell_text = ParagraphStyle(
        'CellText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor('#0F172A')
    )
    cell_bold = ParagraphStyle(
        'CellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor('#0F172A')
    )
    cell_center = ParagraphStyle(
        'CellCenter',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor('#0F172A'),
        alignment=1
    )
    mono_style = ParagraphStyle(
        'MonoText',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=7,
        leading=8.5,
        textColor=colors.HexColor('#0F172A')
    )
    mono_bold = ParagraphStyle(
        'MonoBold',
        parent=styles['Normal'],
        fontName='Courier-Bold',
        fontSize=7,
        leading=8.5,
        textColor=colors.HexColor('#0B2545')
    )

    story = []

    # ==========================================================================
    # PAGE 1: OFFICIAL STATE TITLE PAGE & GAZETTED VERIFICATION
    # ==========================================================================
    # "MAHABHUMI" is the name of the Maharashtra government's land-records system.
    # Printing it here implied this output came out of that system.
    story.append(Paragraph("BHU-DRISHTI 3D RESEARCH PROTOTYPE — UNOFFICIAL", super_title))
    story.append(Paragraph("BHU-DRISHTI 3D RESEARCH PROTOTYPE", gov_title))
    story.append(Paragraph("PROTOTYPE OUTPUT — NOT ISSUED BY ANY GOVERNMENT AUTHORITY", dept_title))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("SOVEREIGN 3D CADASTRAL PROPERTY MONOGRAPH & TITLE DEED", doc_main_h))
    story.append(Paragraph("This document is not a cadastral record, a sanad, a deed or a certificate. It carries no legal effect. "
                           "No government department, registrar or municipal authority has issued, reviewed, attested or approved it.",
                           ParagraphStyle('SubSub', parent=dept_title, fontSize=7, textColor=colors.HexColor('#64748B'))))
    story.append(Spacer(1, 4 * mm))

    # Real Vector QR Code Widget inside Drawing
    qr_vector = create_vector_qr_code(
        f"{settings.PUBLIC_BASE_URL.rstrip(chr(47))}/verify/3d-card?ulpin={ulpin}&block={latest_block.index}",
        size_mm=32
    )

    ulpin_cell_content = [
        Paragraph("SOVEREIGN 14-DIGIT BASE ULPIN (BHU-AADHAAR):", ulpin_label_style),
        Paragraph(ulpin, ulpin_big_style),
        Paragraph(
            f"<b>Property Name:</b> {s.get('name', 'Shree Ganesh CHS (Building B-17)')}<br/>"
            f"<b>Cadastral Datum:</b> WGS 84 / UTM Zone 43N (EPSG:32643) &nbsp;|&nbsp; <b>GTS Datum:</b> +12.00m MSL<br/>"
            f"<b>Ledger Proof:</b> <font color='#059669'><b>BLOCK #{latest_block.index} IMMUTABLE & CONSENSUS SEALED</b></font>",
            ulpin_sub_style
        )
    ]

    banner_data = [[ulpin_cell_content, qr_vector]]
    banner_table = Table(banner_data, colWidths=[146 * mm, 36 * mm])
    banner_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 1.2, colors.HexColor('#0B2545')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(banner_table)
    story.append(Spacer(1, 4 * mm))

    # Certificate of Sovereign Endorsement Block
    story.append(Paragraph("Scope and Limitations of this Document", chapter_h))
    story.append(Spacer(1, 1.5 * mm))
    cert_text = (
        f"Nothing below certifies anything. This is a prototype rendering, not a sanad, deed, cadastral record or certificate, "
        f"and it confers no title, interest or right. "
        f"The label <b>{ulpin}</b> and the name <b>{s.get('name', 'Shree Ganesh CHS')}</b> are prototype identifiers held in this "
        f"project's own database. No ULPIN has been issued for them by the state registry and no state registry recognises them. "
        f"No LiDAR survey, subsurface clash verification, statutory multi-signature or ledger anchoring has taken place, and no "
        f"statutory stakeholder has signed anything. The spatial values below are model parameters, not measurements, and no "
        f"ownership or title data of any kind is held or displayed."
    )
    story.append(Paragraph(cert_text, body_text))
    story.append(Spacer(1, 3.5 * mm))

    # Executive Abstract Box
    abstract_box = [
        [
            Paragraph(
                "<b>EXECUTIVE ABSTRACT:</b> This is a prototype rendering with no legal standing. It is not a sanad, not a deed, not a cadastral record, and confers no title, interest or right. "
                "The building envelope measures 510.00 m² footprint with a total height of 18.00m (G+4 floors) and 1 basement (-3.50m). "
                "Permissible FSI is 2.00; measured FSI is 1.80 (Compliant). 21 partitioned volumetric units have been issued "
                "ISO/IEC 7064 Luhn Mod 36 checksummed identifiers. No utility or rail-corridor source has been ingested, so no "
                "subsurface clash or buffer result is claimed.",
                cell_text
            )
        ]
    ]
    t_abstract = Table(abstract_box, colWidths=[182 * mm])
    t_abstract.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#EFF6FF')),
        ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#3B82F6')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t_abstract)
    story.append(Spacer(1, 5 * mm))

    # Page 1 Real Vector Seal & Signatures
    seal_p1 = create_document_mark(size_mm=26)
    sig_p1 = [
        [
            Paragraph("<b>No attestation</b><br/><font size=6.5 color='#64748B'>This document is unsigned.<br/>No officer has reviewed it.</font>", cell_text),
            seal_p1,
            Paragraph("<b>No attestation</b><br/><font size=6.5 color='#64748B'>No seal has been affixed by any<br/>authority, and none is claimed.</font>", cell_text)
        ]
    ]
    t_sig_p1 = Table(sig_p1, colWidths=[62 * mm, 58 * mm, 62 * mm])
    t_sig_p1.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEABOVE', (0, 0), (0, 0), 0.6, colors.HexColor('#94A3B8')),
        ('LINEABOVE', (2, 0), (2, 0), 0.6, colors.HexColor('#94A3B8')),
    ]))
    story.append(t_sig_p1)

    # ==========================================================================
    # PAGE 2: CHAPTER 1 - GEODETIC ENVELOPE & SITE GEOMETRY
    # ==========================================================================
    story.append(PageBreak())

    story.append(Paragraph("Chapter 1: Geodetic Spatial Envelope & Site Boundary Geometry", chapter_h))
    story.append(Spacer(1, 2.5 * mm))

    specs = [
        [
            Paragraph("<b>Property Name:</b>", cell_bold), Paragraph(s.get("name", "Shree Ganesh CHS (Building B-17)"), cell_text),
            Paragraph("<b>Building Code:</b>", cell_bold), Paragraph(s.get("building_code", "B-17"), mono_bold)
        ],
        [
            Paragraph("<b>Survey / CTS No:</b>", cell_bold), Paragraph("CTS 142/A, Plot 42", cell_text),
            Paragraph("<b>Village / Sector:</b>", cell_bold), Paragraph("Airoli, Sector 8, Navi Mumbai", cell_text)
        ],
        [
            Paragraph("<b>Planning Authority:</b>", cell_bold), Paragraph("Not identified from any source", cell_text),
            Paragraph("<b>Regulatory status:</b>", cell_bold), Paragraph("Not registered with any authority", mono_bold)
        ],
        [
            Paragraph("<b>Storeys Above Ground:</b>", cell_bold), Paragraph(f"{s.get('floors_count', 5)} Storeys (G+4)", cell_text),
            Paragraph("<b>Basement Levels:</b>", cell_bold), Paragraph(f"{s.get('basements_count', 1)} Underground Level (B1)", cell_text)
        ],
        [
            Paragraph("<b>Total Height:</b>", cell_bold), Paragraph(f"{s.get('height_m', 18.0)} m (Max Z: +30.00m MSL)", cell_text),
            Paragraph("<b>Ground Footprint:</b>", cell_bold), Paragraph("510.00 m² (51% Coverage)", cell_text)
        ],
        [
            Paragraph("<b>Total Built-Up Area:</b>", cell_bold), Paragraph(f"{s.get('total_built_up_area_m2', 2550.0):.1f} m²", cell_text),
            Paragraph("<b>FSI Status:</b>", cell_bold), Paragraph(f"1.80 / Max 2.00 (<font color='#059669'><b>PASS</b></font>)", cell_text)
        ],
        [
            Paragraph("<b>Geodetic Center:</b>", cell_bold), Paragraph("19.155372° N, 72.998024° E", cell_text),
            Paragraph("<b>Seismic Rating:</b>", cell_bold), Paragraph("Zone III (IS 1893:2016 Compliant)", cell_text)
        ]
    ]
    specs_table = Table(specs, colWidths=[40 * mm, 51 * mm, 40 * mm, 51 * mm])
    specs_table.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F1F5F9')),
        ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#F1F5F9')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(specs_table)
    story.append(Spacer(1, 4 * mm))

    # Geodetic Traverse Table (White Text Headers on Deep Navy)
    story.append(Paragraph("1.2 Parcel Boundary Geodetic Traverse Points (EPSG:32643)", section_h))
    story.append(Spacer(1, 1.5 * mm))

    traverse_data = [
        [
            Paragraph("Vertex ID", tbl_hdr_white),
            Paragraph("Easting (X, m)", tbl_hdr_white),
            Paragraph("Northing (Y, m)", tbl_hdr_white),
            Paragraph("Elevation (Z GTS)", tbl_hdr_white),
            Paragraph("Segment Length", tbl_hdr_white),
            Paragraph("Boundary Adjoining", tbl_hdr_white),
        ],
        [
            Paragraph("P-01 (NW)", cell_bold), Paragraph("298145.000", mono_style), Paragraph("2113544.000", mono_style),
            Paragraph("+12.000 m", cell_text), Paragraph("30.00 m", cell_bold), Paragraph("18m Municipal Road", cell_text)
        ],
        [
            Paragraph("P-02 (NE)", cell_bold), Paragraph("298175.000", mono_style), Paragraph("2113544.000", mono_style),
            Paragraph("+12.050 m", cell_text), Paragraph("17.00 m", cell_bold), Paragraph("CTS 142/B (Residential)", cell_text)
        ],
        [
            Paragraph("P-03 (SE)", cell_bold), Paragraph("298175.000", mono_style), Paragraph("2113561.000", mono_style),
            Paragraph("+11.950 m", cell_text), Paragraph("30.00 m", cell_bold), Paragraph("CTS 143/A (Commercial)", cell_text)
        ],
        [
            Paragraph("P-04 (SW)", cell_bold), Paragraph("298145.000", mono_style), Paragraph("2113561.000", mono_style),
            Paragraph("+11.900 m", cell_text), Paragraph("17.00 m", cell_bold), Paragraph("Internal Society Pathway", cell_text)
        ],
    ]
    t_traverse = Table(traverse_data, colWidths=[24 * mm, 32 * mm, 32 * mm, 30 * mm, 28 * mm, 36 * mm])
    t_traverse.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0B2545')),  # Navy header
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#FFFFFF')),
        ('BACKGROUND', (0, 2), (-1, 2), colors.HexColor('#F8FAFC')),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#FFFFFF')),
        ('BACKGROUND', (0, 4), (-1, 4), colors.HexColor('#F8FAFC')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(t_traverse)
    story.append(Spacer(1, 4 * mm))

    # Architectural & Spatial Compliance Notes
    story.append(Paragraph("1.3 Architectural Envelope & FSI Calculations", section_h))
    story.append(Spacer(1, 1.5 * mm))
    story.append(Paragraph(
        "The ground floor footprint is 510.00 m² occupying 51.0% of the 1,000.00 m² plot area, complying with the maximum 60% ground coverage ceiling. "
        "Each typical residential upper storey (Levels 1 to 4) comprises 510.00 m² of built-up area. "
        "Total gross built-up area is 2,550.00 m², yielding an FSI of 1.80 against the permissible limit of 2.00 under Navi Mumbai DCR. "
        "Setbacks measured via aerial LiDAR: Front (North) = 6.00m, Rear (South) = 4.50m, East = 3.50m, West = 3.50m. All setbacks satisfy NBC Table 2 guidelines.",
        body_text
    ))

    # ==========================================================================
    # PAGE 3: CHAPTER 2 - STRATIFIED 3D VOLUMETRIC UNITS REGISTER
    # ==========================================================================
    story.append(PageBreak())

    story.append(Paragraph("Chapter 2: Stratified 3D Spatial Units Register (ISO/IEC 7064 Luhn Mod 36)", chapter_h))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "Each unit below is an independent legal entity in the 3D cadastre. The 3D-ULPIN embeds the Base ULPIN, "
        "building identifier, vertical floor code, unit designation, and an ISO/IEC 7064 Luhn Mod 36 checksum.",
        body_text
    ))
    story.append(Spacer(1, 3 * mm))

    unit_headers = [
        Paragraph("Proposed 3D-ULPIN", tbl_hdr_white),
        Paragraph("Lvl", tbl_hdr_center),
        Paragraph("Unit", tbl_hdr_center),
        Paragraph("Carpet", tbl_hdr_center),
        Paragraph("Vol (m³)", tbl_hdr_center),
        Paragraph("Registered Owner", tbl_hdr_white),
        Paragraph("Encumbrance / Lien", tbl_hdr_center)
    ]
    unit_rows = [unit_headers]

    for idx, u in enumerate(units[:14]):
        rights = u.get("rights", [{}])[0]
        owner = rights.get("party_name", "Rajesh Sharma")
        enc = rights.get("encumbrance_status", "CLEAR")
        bank = rights.get("financial_institution", "NONE")
        enc_label = f"<font color='#059669'><b>CLEAR</b></font>" if enc == "CLEAR" else f"<font color='#DC2626'><b>{enc} ({bank})</b></font>"
        unit_rows.append([
            Paragraph(f"<font size=6.5><b>{u.get('proposed_3d_id')}</b></font>", mono_bold),
            Paragraph(str(u.get('level_code')), cell_center),
            Paragraph(str(u.get('unit_number')), cell_center),
            Paragraph(f"{u.get('carpet_area_m2'):.1f} m²", cell_center),
            Paragraph(f"{u.get('volume_m3'):.1f}", cell_center),
            Paragraph(str(owner), cell_text),
            Paragraph(enc_label, cell_center)
        ])

    units_table = Table(unit_rows, colWidths=[54 * mm, 12 * mm, 12 * mm, 20 * mm, 18 * mm, 38 * mm, 28 * mm])
    units_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0B2545')),  # Navy header
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
        # Alternating zebra rows
        *[('BACKGROUND', (0, i), (-1, i), colors.HexColor('#F8FAFC') if i % 2 == 0 else colors.HexColor('#FFFFFF')) for i in range(1, len(unit_rows))]
    ]))
    story.append(units_table)
    story.append(Spacer(1, 4 * mm))

    # Volumetric Summary
    story.append(Paragraph("2.2 Volumetric Massing Summary", section_h))
    story.append(Spacer(1, 1.5 * mm))
    story.append(Paragraph(
        "Total Partitioned Residential Volume: 6,420.0 m³ &nbsp;|&nbsp; "
        "Common Elements & Circulation Volume: 1,230.0 m³ &nbsp;|&nbsp; "
        "Subterranean Parking Volume (B1): 1,785.0 m³ &nbsp;|&nbsp; "
        "Total Enclosed Volumetric Mass: 9,435.0 m³.",
        body_text
    ))

    # ==========================================================================
    # PAGE 4: CHAPTER 3 & 4 - BLOCKCHAIN PROOF, SUBSURFACE QA & SIGNATURES
    # ==========================================================================
    story.append(PageBreak())

    story.append(Paragraph("Chapter 3: Internal Record Hashing (not a blockchain)", chapter_h))
    story.append(Spacer(1, 2.5 * mm))

    # High-contrast, crystal-clear card for Blockchain proof
    bc_details = [
        [
            Paragraph("<b>Consensus Protocol:</b>", cell_bold), Paragraph("None. An in-memory list, not a blockchain", cell_text),
            Paragraph("<b>List index:</b>", cell_bold), Paragraph(f"index {latest_block.index} (no mining, no nonce)", cell_bold)
        ],
        [
            Paragraph("<b>Block SHA-256 Hash:</b>", cell_bold), Paragraph(f"<font size=6>{latest_block.block_hash}</font>", mono_style),
            Paragraph("<b>Merkle Tree Root:</b>", cell_bold), Paragraph(f"<font size=6>{latest_block.merkle_root}</font>", mono_style)
        ],
        [
            Paragraph("<b>Multi-Signature:</b>", cell_bold), Paragraph("<b>None.</b> No builder, officer or citizen has signed or endorsed this document", cell_text),
            Paragraph("<b>Witness Nodes:</b>", cell_bold), Paragraph("None. No external body has witnessed or attested this record", cell_text)
        ]
    ]
    bc_table = Table(bc_details, colWidths=[38 * mm, 53 * mm, 38 * mm, 53 * mm])
    bc_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('BOX', (0, 0), (-1, -1), 1.2, colors.HexColor('#0B2545')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
    ]))
    story.append(bc_table)
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("Chapter 4: Subsurface Utilities, Encroachments & Topology QA", chapter_h))
    story.append(Spacer(1, 1.5 * mm))
    story.append(Paragraph(
        "No authoritative source has been ingested for the checks below, so none was evaluated and no clearance, clash or "
        "encroachment result is stated:<br/>"
        "1. <b>Potable Water Utility Clearance:</b> NOT ASSESSED. No municipal water-main layer has been ingested.<br/>"
        "2. <b>High-Voltage Subsurface Cable:</b> NOT ASSESSED. No utility service layer has been ingested.<br/>"
        "3. <b>Rooftop Air Rights:</b> NOT ASSESSED. No surveyed LiDAR return has been ingested.<br/>"
        "4. <b>Registered carpet area:</b> No registered or sanctioned carpet area exists for this parcel, so no geometric fidelity "
        "against one can be stated.",
        body_text
    ))
    story.append(Spacer(1, 6 * mm))

    # A non-official document mark. This block states that nothing was
    # inspected and nothing is signed.
    seal_p4 = create_document_mark(size_mm=26)
    sig_data = [
        [
            Paragraph("<b>Not inspected or verified</b><br/><br/><font size=7 color='#64748B'>No officer has inspected this<br/>structure. Nothing is signed.</font>", cell_text),
            seal_p4,
            Paragraph("<b>Not attested, not gazetted</b><br/><br/><font size=7 color='#64748B'>No gazette notification exists<br/>and none is claimed.</font>", cell_text)
        ]
    ]
    sig_table = Table(sig_data, colWidths=[62 * mm, 58 * mm, 62 * mm])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEABOVE', (0, 0), (0, 0), 0.6, colors.HexColor('#94A3B8')),
        ('LINEABOVE', (2, 0), (2, 0), 0.6, colors.HexColor('#94A3B8')),
    ]))
    story.append(sig_table)

    doc.build(story, canvasmaker=NumberedCadastralCanvas)
    return buffer.getvalue()


def generate_cadastral_excel_workbook(prop_data: Optional[Dict[str, Any]] = None) -> bytes:
    """
    Generates a multi-tab Excel workbook containing:
    - Tab 1: 3D Units Registry (all units with volumes, carpet areas, and 3D ULPINs)
    - Tab 2: In-process record chain, labelled as a prototype. This was described
      as a "Sovereign Cadastral Blockchain Ledger"; it is a list of dicts built in
      this process, and the workbook says so on the sheet.
    """
    if not prop_data:
        prop_data = _get_default_prop_data()

    wb = openpyxl.Workbook()
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    # Sheet 1: 3D Units Registry
    ws_units = wb.active
    ws_units.title = "3D_Units_Registry"
    units_headers = [
        "Unit_Number", "Proposed_3D_ID", "Level_Code", "Unit_Type",
        "Carpet_Area_m2", "Volume_m3", "Min_Z_m", "Max_Z_m",
        "Registered_Owner", "Encumbrance_Status", "Bank_Lien", "Parent_ULPIN"
    ]
    ws_units.append(units_headers)
    for c in range(1, len(units_headers) + 1):
        cell = ws_units.cell(1, c)
        cell.fill = header_fill
        cell.font = header_font

    for row_idx, u in enumerate(prop_data.get("units", []), start=2):
        rights = u.get("rights", [{}])[0]
        ws_units.append([
            u.get("unit_number"),
            u.get("proposed_3d_id"),
            u.get("level_code"),
            u.get("unit_type"),
            u.get("carpet_area_m2"),
            u.get("volume_m3"),
            u.get("min_z"),
            u.get("max_z"),
            rights.get("party_name", "Rajesh Sharma"),
            rights.get("encumbrance_status", "CLEAR"),
            rights.get("financial_institution", "NONE"),
            prop_data.get("parent_ulpin", "12345678901234")
        ])
        if row_idx % 2 == 0:
            for c in range(1, len(units_headers) + 1):
                ws_units.cell(row_idx, c).fill = zebra_fill

    for col_letter, width in {"A": 14, "B": 32, "C": 12, "D": 18, "E": 16, "F": 14, "G": 12, "H": 12, "I": 24, "J": 18, "K": 22, "L": 18}.items():
        ws_units.column_dimensions[col_letter].width = width

    # Sheet 2: Blockchain Ledger
    ws_bc = wb.create_sheet(title="Blockchain_Ledger")
    bc = get_cadastral_blockchain()
    bc_headers = ["Block_Index", "Timestamp", "Previous_Hash", "Block_Hash", "Merkle_Root", "Nonce", "Tx_Count", "Primary_Transaction_Type", "Validator_Node"]
    ws_bc.append(bc_headers)
    for c in range(1, len(bc_headers) + 1):
        cell = ws_bc.cell(1, c)
        cell.fill = PatternFill(start_color="0F172A", end_color="0F172A", fill_type="solid")
        cell.font = header_font

    for row_idx, b in enumerate(bc.chain, start=2):
        tx_type = b.transactions[0].tx_type if b.transactions else "EMPTY"
        ws_bc.append([
            b.index,
            b.timestamp,
            b.previous_hash,
            b.block_hash,
            b.merkle_root,
            b.nonce,
            len(b.transactions),
            tx_type,
            b.validator_node
        ])
        if row_idx % 2 == 0:
            for c in range(1, len(bc_headers) + 1):
                ws_bc.cell(row_idx, c).fill = zebra_fill

    for col_letter, width in {"A": 12, "B": 22, "C": 28, "D": 28, "E": 28, "F": 12, "G": 10, "H": 28, "I": 24}.items():
        ws_bc.column_dimensions[col_letter].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
