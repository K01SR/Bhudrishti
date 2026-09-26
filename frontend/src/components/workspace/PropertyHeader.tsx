import React from 'react';
import { HeroProperty } from '../../types/cadastre';
import { ShieldCheck, QrCode, Download, Play, CheckCircle2, ChevronDown, Printer } from 'lucide-react';
import { useApp } from '../../context/AppContext';
import { PROPERTY_CARD_PDF_URL, PROPERTY_CARD_LATEX_URL, CADASTRAL_EXCEL_URL, IFC_EXPORT_URL } from '../../services/api';

interface Props {
  property: HeroProperty;
  onOpenQR: () => void;
  onProcessProperty: () => void;
  onExport: (format: string) => void;
  onOpenPrintDeed?: () => void;
  isProcessing: boolean;
}

export const PropertyHeader: React.FC<Props> = ({
  property,
  onOpenQR,
  onProcessProperty,
  onExport,
  onOpenPrintDeed,
  isProcessing,
}) => {
  const { permissions } = useApp();
  const canProcess = permissions.canApprove && !isProcessing;
  return (
    <div className="bg-chalk border-b border-ink px-6 py-3.5 shadow-brutal-sm">
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        {/* Left: Identifiers & Badges */}
        <div className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="annotation text-ink-soft">
              Parent Parcel:
            </span>
            <span className="font-mono text-xs font-bold text-ink bg-canvas px-2.5 py-1 rounded-none border-2 border-ink">
              {property.parent_ulpin}
            </span>

            <span className="text-ink-mut font-bold">/</span>

            <span className="annotation text-accent-strong">
              Proposed 3D Extension:
            </span>
            <span className="font-mono text-xs font-bold text-accent-strong bg-accent-faint px-2.5 py-1 rounded-none border-2 border-ink">
              {property.proposed_3d_id}
            </span>

            <span className="flex items-center gap-1 text-[11px] font-bold uppercase bg-emerald-50 text-emerald-700 border-2 border-ink px-2.5 py-0.5 rounded-none">
              <CheckCircle2 className="w-3.5 h-3.5" />
              {property.status}
            </span>

            <span className="text-[11px] font-mono font-bold text-ink-soft bg-canvas border-2 border-ink px-2 py-0.5 rounded-none">
              {property.record_version}
            </span>

            {property.provenance?.is_synthetic ? (
              <span
                className="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest bg-amber-50 text-amber-800 border-2 border-ink px-2 py-0.5 rounded-none"
                title={property.provenance?.source || 'Synthesized Demonstration Model'}
              >
                <span className="w-1.5 h-1.5 rounded-none bg-amber-500" />
                Modeled / Synthetic
              </span>
            ) : (
              <span
                className="inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest bg-emerald-50 text-emerald-800 border-2 border-ink px-2 py-0.5 rounded-none"
                title={property.provenance?.source || 'Verified Cadastral Survey'}
              >
                <span className="w-1.5 h-1.5 rounded-none bg-emerald-500" />
                Verified Source
              </span>
            )}
          </div>

          <div className="flex items-center gap-3 text-xs text-ink-soft">
            <span>
              Structure: <strong className="text-ink">{property.structure.name}</strong>
            </span>
            <span className="text-ink-mut">•</span>
            <span>
              Precinct: <strong className="text-ink">{property.precinct.name}</strong>
            </span>
            <span className="text-ink-mut">•</span>
            <span className="flex items-center gap-1 text-emerald-700 font-bold">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
              Ed25519 Signed Record
            </span>
          </div>
        </div>

        {/* Right: Action Buttons */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Process Property Button — internal officer pipelines only */}
          {canProcess && (
            <button
              onClick={onProcessProperty}
              disabled={isProcessing}
              className={`flex items-center gap-1.5 px-3.5 py-2 rounded-none text-xs font-bold text-white shadow-brutal-sm transition ${
                isProcessing
                  ? 'bg-accent cursor-not-allowed opacity-60'
                  : 'bg-accent hover:bg-accent-strong shadow-brutal-sm'
              }`}
              title="Runs automated multi-stage AI extraction and validation"
            >
              <Play className={`w-3.5 h-3.5 ${isProcessing ? 'animate-spin' : ''}`} />
              {isProcessing ? 'Processing Pipeline...' : 'Process Property'}
            </button>
          )}

          {/* QR Verification Proof Button */}
          <button
            onClick={onOpenQR}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-none bg-emerald-600 hover:bg-emerald-700 text-ink text-xs font-bold shadow-brutal-sm transition"
            title="Generates public verification QR code and cryptographic receipt"
          >
            <QrCode className="w-3.5 h-3.5" />
            Verify QR Proof
          </button>

          {/* Print Monograph modal trigger (unregistered prototype output) */}
          {onOpenPrintDeed && (
            <button
              onClick={onOpenPrintDeed}
              className="flex items-center gap-1.5 px-3.5 py-2 rounded-none bg-ink hover:bg-ink text-white text-xs font-bold shadow-brutal-sm transition"
              title="View and print the official Government 3D Deed & Technical Monograph"
            >
              <Printer className="w-3.5 h-3.5" />
              Print Monograph (Deed)
            </button>
          )}

          {/* Official 3D Deed (PDF) Direct Download */}
          <a
            href={PROPERTY_CARD_PDF_URL(property.parent_ulpin)}
            download={`Bhu_Drishti_3D_Property_Card_${property.parent_ulpin}.pdf`}
            className="flex items-center gap-1.5 px-3.5 py-2 rounded-none bg-ink hover:bg-ink text-white text-xs font-bold shadow-brutal-sm transition"
            title="Download official Government of Maharashtra 3D Cadastral Property Card PDF"
          >
            <Download className="w-3.5 h-3.5" />
            3D Deed (PDF)
          </a>

          {/* Export Menu — privileged roles only */}
          {permissions.canExport && (
          <div className="relative group">
            <button className="flex items-center gap-1.5 px-3 py-2 rounded-none bg-canvas hover:bg-canvas text-ink text-xs font-bold border-2 border-ink shadow-brutal-sm transition">
              <Download className="w-3.5 h-3.5 text-ink-soft" />
              <span>Export</span>
              <ChevronDown className="w-3 h-3 text-ink-mut" />
            </button>
            <div className="absolute right-0 top-full mt-1.5 w-60 bg-chalk border-2 border-ink rounded-none shadow-brutal py-1.5 hidden group-hover:block z-50">
              {onOpenPrintDeed && (
                <button
                  onClick={onOpenPrintDeed}
                  className="w-full text-left px-3.5 py-2 text-xs font-bold text-accent-strong hover:bg-accent-faint transition flex items-center gap-2"
                >
                  <Printer className="w-3.5 h-3.5" />
                  <span>Print Gazetted Monograph</span>
                </button>
              )}
              <a
                href={PROPERTY_CARD_PDF_URL(property.parent_ulpin)}
                download={`Property_Card_3D_${property.parent_ulpin}.pdf`}
                className="block w-full text-left px-3.5 py-2 text-xs font-bold text-accent-strong hover:bg-accent-faint transition"
              >
                Official 3D Deed (PDF)
              </a>
              <a
                href={PROPERTY_CARD_LATEX_URL(property.parent_ulpin)}
                download={`Property_Card_3D_${property.parent_ulpin}.tex`}
                className="block w-full text-left px-3.5 py-2 text-xs font-bold text-ink hover:bg-canvas transition"
              >
                LaTeX Source (.tex)
              </a>
              <a
                href={CADASTRAL_EXCEL_URL}
                download="Bhu_Drishti_Cadastral_Register.xlsx"
                className="block w-full text-left px-3.5 py-2 text-xs font-bold text-emerald-700 hover:bg-emerald-50 transition"
              >
                Cadastral Register (Excel .xlsx)
              </a>
              <a
                href={IFC_EXPORT_URL(property.parent_ulpin)}
                download={`Bhu_Drishti_3D_${property.parent_ulpin}.ifc`}
                className="block w-full text-left px-3.5 py-2 text-xs font-bold text-accent-strong hover:bg-accent-faint transition"
              >
                IFC 4.3 BIM Model (.ifc)
              </a>
              <div className="border-t border-ink my-1"></div>
              <button
                onClick={() => onExport('cityjson')}
                className="w-full text-left px-3.5 py-2 text-xs font-bold text-ink hover:bg-accent-faint hover:text-accent-strong transition"
              >
                CityJSON 1.1 (3D OGC)
              </button>
              <button
                onClick={() => onExport('geojson')}
                className="w-full text-left px-3.5 py-2 text-xs font-bold text-ink hover:bg-accent-faint hover:text-accent-strong transition"
              >
                GeoJSON (2D Parcels)
              </button>
              <button
                onClick={() => onExport('canonical-json')}
                className="w-full text-left px-3.5 py-2 text-xs font-bold text-ink hover:bg-accent-faint hover:text-accent-strong transition"
              >
                Canonical Property JSON
              </button>
              <button
                onClick={() => onExport('csv')}
                className="w-full text-left px-3.5 py-2 text-xs font-bold text-ink hover:bg-accent-faint hover:text-accent-strong transition"
              >
                CSV Tabular Units Summary
              </button>
            </div>
          </div>
          )}
        </div>
      </div>
    </div>
  );
};
