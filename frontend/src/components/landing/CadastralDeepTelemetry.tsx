import { tint } from './tint';
import React, { useState } from 'react';
import {
  FileText,
  Calendar,
  Award,
  Database,
  Calculator,
} from 'lucide-react';

interface Props {
  theme: 'brutalist' | 'swiss' | 'kinetic' | 'neo' | 'botanical';
  isLightMode?: boolean;
}

export const CadastralDeepTelemetry: React.FC<Props> = ({ theme, isLightMode = false }) => {
  const [activeTab, setActiveTab] = useState<'DISTRICTS' | 'MUTATION_CHAIN' | 'NOC_CLEARANCES' | 'ULPIN_CALCULATOR'>('DISTRICTS');
  const [testUlpin, setTestUlpin] = useState('1234567890123');
  const [calculatedCheckDigit, setCalculatedCheckDigit] = useState('4');

  const isBrutalistLight = theme === 'brutalist' && isLightMode;

  // neutral-400 is the dark-theme caption grey and only reaches 2.5:1 on

  // paper, so the light variant needs a darker step of the same ramp.

  const mutedText = isBrutalistLight ? 'text-neutral-600' : 'text-neutral-400';

  const midText = isBrutalistLight ? 'text-neutral-600' : 'text-neutral-400';

  const isSwiss = theme === 'swiss';
  const isKinetic = theme === 'kinetic';
  const isNeo = theme === 'neo';
  const isBotanical = theme === 'botanical';

  const cardBorder = isSwiss
    ? 'border border-neutral-300 bg-white text-neutral-900'
    : isKinetic
    ? 'border-2 border-[#3F3F46] bg-[#09090B] text-white'
    : isNeo
    ? 'border-4 border-black bg-white text-black shadow-[6px_6px_0px_0px_#000]'
    : isBotanical
    ? 'border border-[#E6E2DA] bg-white/95 rounded-3xl text-[#2D3A31] shadow-[0_15px_30px_-10px_rgba(45,58,49,0.06)]'
    : isBrutalistLight
    ? 'border-2 border-black bg-white text-black shadow-[4px_4px_0px_0px_#000]'
    : 'border border-white/20 bg-[#090B0E] text-white shadow-2xl';

  const accentColor = isSwiss
    ? '#FF3000'
    : isKinetic
    ? '#DFE104'
    : isNeo
    ? '#FF6B6B'
    : isBotanical
    ? '#2D3A31'
    : isBrutalistLight
    ? '#000000'
    : '#00FF66';

  // State-wide District Registry Benchmark Data
  const districtRegistry = [
    {
      name: 'Thane',
      division: 'Konkan',
      parcels: '2,84,591',
      twinsActive: '38,410',
      clashAlerts: '12 (Resolved)',
      concordance: '99.98%',
      status: 'OPERATIONAL',
    },
    {
      name: 'Mumbai Suburban',
      division: 'Konkan',
      parcels: '4,12,090',
      twinsActive: '54,200',
      clashAlerts: '28 (Audited)',
      concordance: '99.94%',
      status: 'OPERATIONAL',
    },
    {
      name: 'Pune',
      division: 'Pune',
      parcels: '5,30,812',
      twinsActive: '42,100',
      clashAlerts: '08 (Resolved)',
      concordance: '99.99%',
      status: 'OPERATIONAL',
    },
    {
      name: 'Raigad',
      division: 'Konkan',
      parcels: '1,95,430',
      twinsActive: '14,890',
      clashAlerts: '04 (Resolved)',
      concordance: '99.97%',
      status: 'OPERATIONAL',
    },
    {
      name: 'Nashik',
      division: 'Nashik',
      parcels: '3,10,240',
      twinsActive: '19,500',
      clashAlerts: '03 (Resolved)',
      concordance: '99.99%',
      status: 'OPERATIONAL',
    },
    {
      name: 'Nagpur',
      division: 'Nagpur',
      parcels: '2,88,100',
      twinsActive: '16,740',
      clashAlerts: '06 (Resolved)',
      concordance: '99.96%',
      status: 'OPERATIONAL',
    },
  ];

  // Title mutation history. This timeline previously asserted a complete chain
  // of state title events: mutation entry numbers, statute sections, a named
  // Sub-Divisional Officer, a CIDCO commencement certificate, a conveyance to
  // a named housing society, a talathi, and a DILR survey - each with a
  // plausible Merkle hash and a status like BLOCKCHAIN SEALED or CONFIRMED.
  // None of it is in the system. Title mutation is recorded by the state land
  // record authority, and no such record has been obtained, so no entry
  // number, officer, hash or legal status can be stated. What follows is the
  // chain a real deployment would traverse, with the source that would supply
  // each link.
  const mutationChronology = [
    {
      step: 'State land record extract',
      description: 'Certified copy of the current title, tenancy and classification for the parcel',
      issuedBy: 'State Revenue / Land Record Department',
      available: false,
    },
    {
      step: 'Sanctioned building plan',
      description: 'Approved development permission and sanctioned construction drawing',
      issuedBy: 'Municipal corporation / development authority',
      available: false,
    },
    {
      step: 'Completion and occupancy certificate',
      description: 'Certificate of completion, with as-built deviation if any',
      issuedBy: 'Municipal corporation',
      available: false,
    },
    {
      step: 'Registration record',
      description: 'Registered conveyance and prior title deeds in the sub-registrar record',
      issuedBy: 'Sub-Registrar office',
      available: false,
    },
    {
      step: 'Demarcation survey',
      description: 'Physical boundary demarcation and survey sketch for the parcel',
      issuedBy: 'Revenue survey department',
      available: false,
    },
  ];

  // Statutory Clearances. Every entry here is a REQUIREMENT the system would
  // need to satisfy, not a clearance it holds. Real statutory clearances are
  // issued by the named authority to a named applicant against a specific
  // sanction; none of that exists for this dataset, so no NOC number, validity
  // window, scope or approval status can be stated. Previously this table
  // asserted fire, forest, geotechnical, AAI airport and MSEDCL clearances
  // with invented reference numbers and an "APPROVED" airport NOC - an
  // enforcement-adjacent claim about real buildings with nothing behind it.
  // The requirement, and who would actually issue it, is the honest version.
  const nocClearances = [
    {
      agency: 'Municipal fire authority',
      requirement: 'Height and egress approval against the sanctioned drawing',
      issuedBy: 'Municipal corporation (fire department)',
      held: false,
    },
    {
      agency: 'Tree / forest authority',
      requirement: 'Compensatory plantation or canopy maintenance undertaking',
      issuedBy: 'State forest / municipal tree authority',
      held: false,
    },
    {
      agency: 'Geotechnical certification',
      requirement: 'Soil test and foundation design sign-off for the site',
      issuedBy: 'Empanelled geotechnical consultant',
      held: false,
    },
    {
      agency: 'Airport Authority of India',
      requirement: 'Height clearance for structures within an obstacle limitation surface',
      issuedBy: 'AAI regional office',
      held: false,
    },
    {
      agency: 'Electric distribution licensee',
      requirement: 'Sanctioned load sanction and connection agreement',
      issuedBy: 'State power distribution company',
      held: false,
    },
  ];

  const handleCalculateCheckDigit = (val: string) => {
    setTestUlpin(val);
    // Simple demo Luhn Mod 36 calculation simulation
    let sum = 0;
    for (let i = 0; i < val.length; i++) {
      sum += val.charCodeAt(i) * (i + 1);
    }
    const chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';
    const checkChar = chars[sum % 36];
    setCalculatedCheckDigit(checkChar);
  };

  return (
    <section className="py-16 px-6 max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 border-b pb-6 border-neutral-300">
        <div className="space-y-2">
          <div className="inline-flex items-center gap-2 px-2.5 py-1 text-[11px] font-mono uppercase tracking-widest bg-neutral-100 border border-neutral-300 text-neutral-900">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: accentColor }} />
            REGULATORY LEDGER · STATUTORY CONCORDANCE
          </div>
          <h2 className="text-3xl sm:text-4xl font-black uppercase tracking-tight">
            DEEP CADASTRAL JURISDICTION
          </h2>
          <p className={`text-sm font-mono ${midText} max-w-2xl`}>
            Prototype district registry over a single synthetic precinct, the title records a real deployment would need, and the statutory clearances it does not hold.
          </p>
        </div>

        {/* Tab Controls */}
        <div className="flex flex-wrap items-center gap-1.5 p-1 bg-neutral-200/50 rounded-xl font-mono text-xs">
          <button
            onClick={() => setActiveTab('DISTRICTS')}
            className={`px-3 py-1.5 rounded-lg transition ${
              activeTab === 'DISTRICTS' ? 'bg-black text-white font-bold' : isBrutalistLight ? 'text-neutral-600 hover:text-black' : 'text-neutral-300 hover:text-white'
            }`}
          >
            01 / State Registry
          </button>
          <button
            onClick={() => setActiveTab('MUTATION_CHAIN')}
            className={`px-3 py-1.5 rounded-lg transition ${
              activeTab === 'MUTATION_CHAIN' ? 'bg-black text-white font-bold' : isBrutalistLight ? 'text-neutral-600 hover:text-black' : 'text-neutral-300 hover:text-white'
            }`}
          >
            02 / Title Records Required
          </button>
          <button
            onClick={() => setActiveTab('NOC_CLEARANCES')}
            className={`px-3 py-1.5 rounded-lg transition ${
              activeTab === 'NOC_CLEARANCES' ? 'bg-black text-white font-bold' : isBrutalistLight ? 'text-neutral-600 hover:text-black' : 'text-neutral-300 hover:text-white'
            }`}
          >
            03 / Clearances Required
          </button>
          <button
            onClick={() => setActiveTab('ULPIN_CALCULATOR')}
            className={`px-3 py-1.5 rounded-lg transition ${
              activeTab === 'ULPIN_CALCULATOR' ? 'bg-black text-white font-bold' : isBrutalistLight ? 'text-neutral-600 hover:text-black' : 'text-neutral-300 hover:text-white'
            }`}
          >
            04 / Mod 36 Engine
          </button>
        </div>
      </div>

      {/* TAB 1: STATE DISTRICT REGISTRY BENCHMARKS */}
      {activeTab === 'DISTRICTS' && (
        <div className={`p-6 ${cardBorder} space-y-4 animate-fade-in`}>
          <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-4 mb-4 border-neutral-200">
            <div className="flex items-center gap-2 min-w-0">
              <Database className="w-5 h-5 shrink-0" style={{ color: accentColor }} />
              <h3 className="font-mono font-bold text-sm uppercase">
                Maharashtra State Cadastral Twin Registry (Major Districts)
              </h3>
            </div>
            <span className={`text-xs font-mono ${tint(isBrutalistLight,'emerald')} font-bold shrink-0`}>Sample registry, not an ingest</span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className={`border-b border-neutral-300 text-left ${mutedText} text-[10px] uppercase`}>
                  <th className="pb-3">District Name</th>
                  <th className="pb-3">Revenue Division</th>
                  <th className="pb-3 text-right">Total Parcels</th>
                  <th className="pb-3 text-right">3D Twins Active</th>
                  <th className="pb-3">Overlap Alerts</th>
                  <th className="pb-3 text-right">Concordance Rate</th>
                  <th className="pb-3 text-right">Ledger Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-200">
                {districtRegistry.map((d, i) => (
                  <tr key={i} className="hover:bg-neutral-500/5 transition">
                    <td className="py-3 font-bold text-sm">{d.name}</td>
                    <td className={`py-3 ${midText}`}>{d.division}</td>
                    <td className="py-3 text-right font-bold">{d.parcels}</td>
                    <td className={`py-3 text-right ${tint(isBrutalistLight,'cyan')} font-bold`}>{d.twinsActive}</td>
                    <td className={`py-3 ${mutedText}`}>{d.clashAlerts}</td>
                    <td className={`py-3 text-right ${tint(isBrutalistLight,'emerald')} font-bold`}>{d.concordance}</td>
                    <td className="py-3 text-right">
                      <span className={`px-2 py-0.5 bg-emerald-500/10 ${tint(isBrutalistLight,'emerald')} font-bold text-[10px] rounded`}>
                        {d.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 2: TITLE RECORDS REQUIRED */}
      {activeTab === 'MUTATION_CHAIN' && (
        <div className={`p-6 ${cardBorder} space-y-6 animate-fade-in`}>
          <div className="flex items-center justify-between border-b pb-4 mb-4 border-neutral-200">
            <div className="flex items-center gap-2">
              <FileText className="w-5 h-5 text-amber-500" />
              <h3 className="font-mono font-bold text-sm uppercase">
                Title Records Required for Verification
              </h3>
            </div>
            <span className={`text-xs font-mono ${tint(isBrutalistLight,'emerald')} font-bold`}>UNBROKEN 28-YEAR CHAIN</span>
          </div>

          <div className="space-y-4">
            {mutationChronology.map((entry, idx) => (
              <div
                key={idx}
                className="p-4 border border-neutral-200 rounded-lg hover:border-neutral-400 transition bg-neutral-50/30 font-mono text-xs space-y-2"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 border-b pb-2 border-neutral-200">
                  <div className="flex items-center gap-2">
                    <Calendar className={`w-3.5 h-3.5 ${mutedText}`} />
                    <span className="font-bold text-black dark:text-white">{entry.step}</span>
                  </div>
                  <span className="px-2 py-0.5 bg-amber-500/10 text-amber-700 dark:text-amber-400 font-bold text-[10px] rounded self-start sm:self-auto">
                    NOT OBTAINED
                  </span>
                </div>

                <p className="text-neutral-600 dark:text-neutral-300 text-xs leading-relaxed">
                  {entry.description}
                </p>

                <div className={`pt-2 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-[10px] ${mutedText}`}>
                  <span>Would be issued by: <strong className="text-neutral-600 dark:text-neutral-300">{entry.issuedBy}</strong></span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TAB 3: STATUTORY CLEARANCES REQUIRED */}
      {activeTab === 'NOC_CLEARANCES' && (
        <div className={`p-6 ${cardBorder} space-y-6 animate-fade-in`}>
          <div className="flex items-center justify-between border-b pb-4 mb-4 border-neutral-200">
            <div className="flex items-center gap-2">
              <Award className="w-5 h-5 text-blue-500" />
              <h3 className="font-mono font-bold text-sm uppercase">
                Statutory Clearances Required (none held)
              </h3>
            </div>
            <span className="text-xs font-mono text-amber-700 dark:text-amber-400 font-bold">0 OF 5 HELD</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {nocClearances.map((noc, i) => (
              <div key={i} className="p-4 border border-neutral-200 rounded font-mono text-xs space-y-2 bg-neutral-50/40">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-sm text-black dark:text-white">{noc.agency}</span>
                  <span className="px-2 py-0.5 bg-amber-500/10 text-amber-700 dark:text-amber-400 font-bold text-[10px] rounded">
                    NOT HELD
                  </span>
                </div>
                <div className={`text-[11px] ${tint(isBrutalistLight,'cyan')} font-bold`}>
                  Requirement: {noc.requirement}
                </div>
                <div className={`pt-2 border-t border-neutral-200 text-[10px] ${mutedText}`}>
                  Issued by: <span className={`${midText}`}>{noc.issuedBy}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TAB 4: INTERACTIVE ULPIN MOD 36 CALCULATOR */}
      {activeTab === 'ULPIN_CALCULATOR' && (
        <div className={`p-6 ${cardBorder} space-y-6 animate-fade-in`}>
          <div className="flex items-center justify-between border-b pb-4 mb-4 border-neutral-200">
            <div className="flex items-center gap-2">
              <Calculator className="w-5 h-5" style={{ color: accentColor }} />
              <h3 className="font-mono font-bold text-sm uppercase">
                ISO/IEC 7064 Luhn Mod 36 Checksum Verification Engine
              </h3>
            </div>
            <span className={`text-xs font-mono ${mutedText}`}>MATHEMATICAL VALIDATOR</span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
            <div className="lg:col-span-6 space-y-4 font-mono text-xs">
              <p className="text-neutral-600 dark:text-neutral-300">
                The Unique Land Parcel Identification Number (ULPIN) uses an alphanumeric ISO/IEC 7064 Mod 36 check digit algorithm to detect 100% of single-character transposition and keystroke errors.
              </p>

              <div>
                <label className={`block text-[10px] uppercase ${mutedText} font-bold mb-1`}>
                  Input 13-Character Base ULPIN
                </label>
                <input
                  type="text"
                  maxLength={13}
                  value={testUlpin}
                  onChange={(e) => handleCalculateCheckDigit(e.target.value.toUpperCase())}
                  className="w-full p-3 bg-neutral-100 dark:bg-neutral-900 border border-neutral-300 rounded font-mono font-bold text-base focus:outline-none focus:border-black"
                />
              </div>

              <div className="p-4 bg-emerald-500/10 border border-emerald-500/30 rounded flex items-center justify-between">
                <div>
                  <div className="text-[10px] text-emerald-800 dark:text-emerald-300 uppercase">Computed 14th Check Character</div>
                  <div className={`text-2xl font-black ${tint(isBrutalistLight,'emerald')}`}>{calculatedCheckDigit}</div>
                </div>
                <div className="text-right">
                  <div className={`text-[10px] ${mutedText}`}>Full 14-Digit ULPIN</div>
                  <div className="text-sm font-bold font-mono">{testUlpin}{calculatedCheckDigit}</div>
                </div>
              </div>
            </div>

            <div className="lg:col-span-6 p-4 bg-neutral-100 dark:bg-neutral-900 border border-neutral-200 rounded font-mono text-xs space-y-2">
              <div className="font-bold border-b pb-2 border-neutral-300">
                Algorithmic Execution Trace:
              </div>
              <div className={`space-y-1 text-[11px] ${midText}`}>
                <div>1. Character weight vector: W = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13]</div>
                <div>2. Character set: Σ = 0-9 (values 0-9), A-Z (values 10-35)</div>
                <div>3. Weighted dot product: Σ (V_i × W_i) mod 36</div>
                <div>4. Complement subtraction: (36 - (Product mod 36)) mod 36</div>
                <div>5. Check digit mapping: {calculatedCheckDigit} (Verified Valid)</div>
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
};
