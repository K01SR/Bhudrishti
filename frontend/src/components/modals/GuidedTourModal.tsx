import React, { useState } from 'react';
import { 
  X, 
  ChevronRight, 
  ChevronLeft, 
  Play, 
  ArrowRight
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { DEMO_ULPIN } from '../../constants';

interface TourScene {
  number: number;
  timeRange: string;
  title: string;
  category: string;
  talkingPoints: string[];
  keyHighlight: string;
  recommendedAction: string;
  actionRoute?: string;
}

const TOUR_SCENES: TourScene[] = [
  {
    number: 1,
    timeRange: "0:00 - 0:45",
    title: "Domain Positioning & Official 14-Char ULPIN Anchor",
    category: "FOUNDATION",
    talkingPoints: [
      "Clarify immediately: this showcase uses a prototype parcel identifier, not a real ULPIN. No registry has issued it.",
      "We anchor the parent parcel identifier immutably to define the surface parcel bounds (1,000 m²).",
      "Introduce the 'Proposed Bhu-Drishti 3D Spatial Extension': {parent}/{TYPE}{BUILDING}-{LEVEL}-{UNIT}-{CHECK}.",
      `Demonstrate Luhn Mod 36 checksum calculation on Flat 501: ${DEMO_ULPIN}/UB17-L05-501-U.`
    ],
    keyHighlight: "The map is the interface. The property registry + spatial intelligence + verification workflow is the product.",
    recommendedAction: "Open 3D Workspace to inspect Parent ULPIN and Proposed 3D ID",
    actionRoute: "/workspace",
  },
  {
    number: 2,
    timeRange: "0:45 - 1:30",
    title: "Multi-Source Spatial Evidence Ingestion (6 Streams)",
    category: "INGESTION",
    talkingPoints: [
      "Open Evidence Tab: Display all 6 live heterogeneous sources.",
      "1. GIS Cadastre vector polygon (EPSG:7755 / UTM Zone 43N).",
      "2. Drone Photogrammetry (Epoch 1 & 2 at 2.5 cm GSD).",
      "3. Airborne LiDAR (32.4 pts/m² classified point cloud).",
      "4. CAD Floorplans (DWG room layouts for Floors 1–5 & Basement B1).",
      "5. Survey of India (SoI) CORS GNSS ground control monuments.",
      "6. DEM/DSM elevation terrain model at 0.5m resolution."
    ],
    keyHighlight: "All 6 streams carry cryptographically verifiable ingestion hashes, capture dates, and CRS definitions.",
    recommendedAction: "Switch to Evidence Tab in Property Workspace",
    actionRoute: "/workspace",
  },
  {
    number: 3,
    timeRange: "1:30 - 2:30",
    title: "Volumetric 3D Twin & Exploded Vertical Strata",
    category: "3D CADASTRE",
    talkingPoints: [
      "Demonstrate Three.js volumetric rendering with smooth orbit and pan.",
      "Drag Explode Slider: Watch the 5 floors separate vertically into floating strata levels.",
      "Click on Flat 201: Show discrete 3D bounding box (Z = 7.2m to 10.8m).",
      "Switch to Rights Layer: Highlight Flat 201 with active State Bank of India mortgage (₹85,00,000 lien) and western corridor easement."
    ],
    keyHighlight: "Every vertical apartment is an independent ISO 19107 legal solid, not a generic 3D model.",
    recommendedAction: "Engage Explode Slider and Inspect Flat 201 in Workspace",
    actionRoute: "/workspace",
  },
  {
    number: 4,
    timeRange: "2:30 - 3:15",
    title: "Subterranean X-Ray & Utility Clash Detection",
    category: "SPATIAL QA",
    talkingPoints: [
      "Toggle Underground X-Ray: Ground fades to reveal basement (Z = -3.0m) and utility pipes.",
      "Showcase Subterranean Clash: Stormwater Drainage Pipe PIPE-DRAIN-01 collides with basement at Z = -3.2m.",
      "Open 'Ask the Map' modal: Type 'Show underground clashes' and watch camera fly automatically to the collision point.",
      "Show Rule R009 (Subterranean Utility Clearance) flagged in real-time."
    ],
    keyHighlight: "Real-time 3D boolean intersection prevents catastrophic infrastructure drilling accidents.",
    recommendedAction: "Toggle Underground X-Ray in 3D Workspace",
    actionRoute: "/workspace",
  },
  {
    number: 5,
    timeRange: "3:15 - 3:45",
    title: "Multi-Epoch AI Change Detection (2026 E1 vs 2027 E2)",
    category: "AI SURVEILLANCE",
    talkingPoints: [
      "Toggle the Time Slider between Epoch 1 and Epoch 2 of the same generated dataset.",
      "A Level 6 massing volume appears in the second epoch, one floor taller than the first.",
      "The classifier labels the difference as an 'unclassified vertical change'.",
      "The difference is flagged for review. Nothing here establishes whether the change was lawful."
    ],
    keyHighlight: "Volumetric differential analysis shows what differs between two epochs of the modelled dataset. Both epochs are generated, so the result is a demonstration of differencing, not a detection of a real illegal construction.",
    recommendedAction: "Toggle Time Slider in Workspace History Tab",
    actionRoute: "/workspace",
  },
  {
    number: 6,
    timeRange: "3:45 - 4:15",
    title: "Review Queue & Decision Actions",
    category: "GOVERNANCE",
    talkingPoints: [
      "Open the review queue: view cases whose status is NEEDS_REVIEW in the demo dataset.",
      "Inspect the B-17 case dossier and the QA findings recorded against it.",
      "Demonstrate the state machine: Approve, Reject, or Request Correction.",
      "A decision updates a demo row and signs it with this prototype's own Ed25519 key. No government officer, district verifier, or authority takes part, and the signature is not a legal attestation."
    ],
    keyHighlight: "Human-in-the-loop authority governance: AI assists and detects, but only authorized officers approve.",
    recommendedAction: "Inspect District Verification Queue",
    actionRoute: "/district",
  },
  {
    number: 7,
    timeRange: "4:15 - 5:00",
    title: "Tamper-Evident SHA-256 Ledger & Public QR Proof",
    category: "PUBLIC TRUST",
    talkingPoints: [
      "Navigate to /audit: Show the SHA-256 tamper-evident hash chain linking all decisions.",
      "Open the signed proof page (/verify/blockchain): a visitor can paste or scan a proof link and check it themselves.",
      "Owner names and bank details are left out of the public proof payload as a deliberate minimisation choice, not a certified compliance claim.",
      "The Ed25519 seal proves this deployment signed those exact fields. It is not a government seal, and signing is not approval."
    ],
    keyHighlight: "Complete end-to-end loop: From raw survey evidence to a signature anyone can independently check.",
    recommendedAction: "View Public Verification Page",
    actionRoute: "/verify/blockchain",
  },
];

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

export const GuidedTourModal: React.FC<Props> = ({ isOpen, onClose }) => {
  const [currentIdx, setCurrentIdx] = useState<number>(0);
  const navigate = useNavigate();

  if (!isOpen) return null;

  const current = TOUR_SCENES[currentIdx];

  const handleAction = () => {
    onClose();
    if (current.actionRoute) {
      navigate(current.actionRoute);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="w-full max-w-2xl bg-white rounded-none border-2 border-ink shadow-brutal overflow-hidden flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 bg-canvas border-b border-ink flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-none bg-ink text-white flex items-center justify-center">
              <Play className="w-3.5 h-3.5 fill-white" />
            </div>
            <div>
              <span className="text-[10px] font-mono font-bold uppercase tracking-widest text-accent-strong block">
                Official Presentation Guide
              </span>
              <h3 className="text-sm font-bold text-ink">
                5-Minute Judge & Authority Walkthrough
              </h3>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-none text-ink-soft hover:text-ink-soft hover:bg-canvas transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scene Content */}
        <div className="p-6 space-y-5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono font-bold bg-accent-faint text-accent-strong border-2 border-ink px-2.5 py-1 rounded-none">
                SCENE {current.number} OF 7
              </span>
              <span className="text-xs font-bold text-ink-soft font-mono">
                [{current.timeRange}]
              </span>
            </div>
            <span className="text-[11px] font-bold text-ink-soft uppercase tracking-widest">
              {current.category}
            </span>
          </div>

          <div>
            <h4 className="text-xl font-bold text-ink">
              {current.title}
            </h4>
            <p className="text-xs font-bold text-ink bg-accent-faint p-3 rounded-none border-2 border-ink mt-3">
              Presentation Anchor: {current.keyHighlight}
            </p>
          </div>

          <div>
            <span className="text-xs font-bold text-ink uppercase tracking-widest block mb-2 font-sans">
              Key Talking Points for Judges:
            </span>
            <ul className="space-y-2 text-xs text-ink-soft">
              {current.talkingPoints.map((pt, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="w-1.5 h-1.5 rounded-none bg-ink mt-1.5 shrink-0"></span>
                  <span className="leading-relaxed">{pt}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Footer Controls */}
        <div className="px-6 py-4 bg-canvas border-t border-ink flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setCurrentIdx((p) => Math.max(0, p - 1))}
              disabled={currentIdx === 0}
              className="px-3 py-2 rounded-none bg-white border-2 border-ink text-ink hover:bg-canvas disabled:opacity-40 disabled:cursor-not-allowed text-xs font-bold flex items-center gap-1 transition"
            >
              <ChevronLeft className="w-4 h-4" />
              <span>Previous</span>
            </button>
            <button
              onClick={() => setCurrentIdx((p) => Math.min(TOUR_SCENES.length - 1, p + 1))}
              disabled={currentIdx === TOUR_SCENES.length - 1}
              className="px-3 py-2 rounded-none bg-white border-2 border-ink text-ink hover:bg-canvas disabled:opacity-40 disabled:cursor-not-allowed text-xs font-bold flex items-center gap-1 transition"
            >
              <span>Next Scene</span>
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>

          <button
            onClick={handleAction}
            className="px-5 py-2.5 rounded-none bg-ink hover:bg-ink-soft text-white text-xs font-bold flex items-center gap-1.5 transition"
          >
            <span>{current.recommendedAction}</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};
