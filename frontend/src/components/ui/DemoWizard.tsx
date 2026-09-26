import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Play, ChevronRight, X, Upload, Box, QrCode, ShieldCheck, Link2 } from 'lucide-react';
import { useDeployment } from '../../services/deployment';

/**
 * Floating guided walkthrough for judges / demos.
 * Narration stays prototype-honest: nothing here claims official registry status.
 */
const STEPS = [
  {
    title: '1. Upload Point Cloud',
    path: '/app/ingest',
    icon: Upload,
    desc:
      'Upload a LAS/LAZ/CSV file. The pipeline runs building extraction and floor segmentation, then returns a prototype-derived ULPIN with provenance.',
  },
  {
    title: '2. View 3D Digital Twin',
    path: '/app/map?view=3d',
    icon: Box,
    desc:
      'Inspect the volumetric twin. Floor fills show modelled rights or verification status — not a registered title.',
  },
  {
    title: '3. ULPIN Identity Card',
    path: '/app/ulpin',
    icon: QrCode,
    desc:
      'Encode/decode the proposed 3D spatial extension ID (Luhn Mod-36). Printable card is a student prototype prop, not a government credential.',
  },
  {
    title: '4. Reviewer Disposition',
    path: '/app/review',
    icon: ShieldCheck,
    desc:
      'A reviewer records acceptance. On accept, a prototype-derived ULPIN and tamper-evident audit proof are surfaced — not a registry allocation.',
  },
  {
    title: '5. Audit Chain',
    path: '/app/audit',
    icon: Link2,
    desc:
      'Events are SHA-256 chained and Ed25519 signed in this deployment. A checksum match proves integrity of these records, not authenticity against a state register.',
  },
] as const;

export const DemoWizard: React.FC = () => {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState(0);
  const navigate = useNavigate();
  const { demo_mode: demoMode } = useDeployment();

  const go = (i: number) => {
    const next = Math.max(0, Math.min(STEPS.length - 1, i));
    navigate(STEPS[next].path);
    setStep(next);
  };

  // The tour walks the generated Airoli scenario, so every stop on it answers
  // 503 while ENABLE_DEMO_MODE is off. Rendering an invitation to a walkthrough
  // whose destinations all refuse is worse than rendering nothing, and on a
  // real-only deployment it advertises affordances that do not exist. Fails
  // closed: useDeployment reports demo_mode false until the fetch resolves.
  if (!demoMode) return null;

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => {
          setOpen(true);
          go(0);
        }}
        className="fixed bottom-20 lg:bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-2.5 bg-accent text-ink font-mono font-bold text-sm border-2 border-ink shadow-brutal hover:shadow-brutal-sm hover:translate-x-[2px] hover:translate-y-[2px] transition-all"
        aria-label="Start guided demo"
      >
        <Play className="w-4 h-4" />
        Start Guided Demo
      </button>
    );
  }

  const cur = STEPS[step];
  const Icon = cur.icon;

  return (
    <div className="fixed bottom-20 lg:bottom-6 right-6 z-50 w-[min(380px,calc(100vw-2rem))] bg-chalk border-2 border-ink shadow-brutal-lg font-mono">
      <div className="flex items-center justify-between px-4 py-2 bg-ink text-chalk text-xs">
        <span className="font-bold uppercase tracking-wider">
          Guided Demo · {step + 1}/{STEPS.length}
        </span>
        <button type="button" onClick={() => setOpen(false)} className="hover:text-accent" aria-label="Close guided demo">
          <X className="w-4 h-4" />
        </button>
      </div>
      <div className="h-1 bg-canvas">
        <div
          className="h-full bg-accent transition-all"
          style={{ width: `${((step + 1) / STEPS.length) * 100}%` }}
        />
      </div>
      <div className="p-4">
        <div className="flex items-center gap-2 mb-2">
          <Icon className="w-5 h-5 text-accent-strong" />
          <h3 className="font-bold text-sm text-ink">{cur.title}</h3>
        </div>
        <p className="text-xs text-ink-soft leading-relaxed">{cur.desc}</p>
        <p className="mt-2 text-[10px] text-ink-mut uppercase tracking-wide">
          Student prototype · not an official government record
        </p>
      </div>
      <div className="flex items-center justify-between px-4 py-3 border-t-2 border-ink">
        <button
          type="button"
          onClick={() => step > 0 && go(step - 1)}
          disabled={step === 0}
          className="text-xs text-ink-soft hover:text-ink disabled:opacity-30"
        >
          ← Back
        </button>
        <div className="flex gap-1.5">
          {STEPS.map((_, i) => (
            <button
              key={STEPS[i].title}
              type="button"
              onClick={() => go(i)}
              className={`w-2 h-2 rounded-none border border-ink ${
                i === step ? 'bg-accent' : i < step ? 'bg-ink/40' : 'bg-ink/15'
              }`}
              aria-label={`Go to step ${i + 1}`}
            />
          ))}
        </div>
        <button
          type="button"
          onClick={() => (step === STEPS.length - 1 ? setOpen(false) : go(step + 1))}
          className="flex items-center gap-1 text-xs font-bold text-accent-strong hover:underline"
        >
          {step === STEPS.length - 1 ? 'Finish' : 'Next'}
          {step < STEPS.length - 1 && <ChevronRight className="w-3 h-3" />}
        </button>
      </div>
    </div>
  );
};
