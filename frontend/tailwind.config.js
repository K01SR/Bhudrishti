/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        /* Page surface is the landing's light paper (#F4F3EE); cards sit on it
           as white. Both were #FFFFFF, so cards had no tonal separation and
           relied entirely on borders for hierarchy. */
        canvas: '#F4F3EE',
        chalk: '#FFFFFF',
        /* Pure black, matching the landing's light variant (`text-black`,
           `border-black`, wireframe 0x0a0a0a). Brutalism treats the border and
           the offset shadow as one object, so the ink has to be true black or
           the effect goes soft. */
        ink: {
          DEFAULT: '#000000',
          soft: '#1A1D23',
          mut: '#5B6472',
          faint: '#A0A6B0',
        },
        /* Variable-driven accent — swap via --accent* in index.html */
        accent: {
          DEFAULT: 'rgb(var(--accent) / <alpha-value>)',
          strong: 'rgb(var(--accent-strong) / <alpha-value>)',
          soft: 'rgb(var(--accent-soft) / <alpha-value>)',
          sky: 'rgb(var(--accent-sky) / <alpha-value>)',
          faint: 'rgba(var(--accent-glow) / 0.06)',
        },
        /* Violation / legal-risk accent. Flat rather than nested: these were
           nested under `gov`, which made Tailwind emit `gov-crimson-600`, while
           every call site uses `text-crimson-600`. `crimson` is not a stock
           Tailwind colour, so all 14 call sites silently rendered unstyled. */
        crimson: {
          50: '#fef2f2',
          100: '#fee2e2',
          200: '#fecaca',
          400: '#f87171',
          500: '#ef4444',
          600: '#dc2626',
          700: '#b91c1c',
        },
        /* Unused. Nested palettes emit `gov-<colour>-<shade>`, which no call
           site uses; `blue`/`slate`/`emerald`/`amber` were silently falling back
           to the stock Tailwind palette and `crimson` resolved to nothing. */
        gov: {
          blue: {
            50: '#eff6ff',
            100: '#dbeafe',
            200: '#bfdbfe',
            500: '#3b82f6',
            600: '#2563eb',
            700: '#1d4ed8',
            800: '#1e40af',
            900: '#1e3a8a',
            950: '#172554',
          },
          slate: {
            25: '#fcfcfd',
            50: '#f8fafc',
            100: '#f1f5f9',
            200: '#e2e8f0',
            300: '#cbd5e1',
            400: '#94a3b8',
            500: '#64748b',
            600: '#475569',
            700: '#334155',
            800: '#1e293b',
            900: '#0f172a',
          },
          emerald: {
            50: '#ecfdf5',
            100: '#d1fae5',
            500: '#10b981',
            600: '#059669',
            700: '#047857',
          },
          amber: {
            50: '#fffbeb',
            100: '#fef3c7',
            500: '#f59e0b',
            600: '#d97706',
            700: '#b45309',
          },
          crimson: {
            50: '#fef2f2',
            100: '#fee2e2',
            500: '#ef4444',
            600: '#dc2626',
            700: '#b91c1c',
          },
        },
        cadastre: {
          light: '#f8fafc',
          card: '#ffffff',
          surface: '#f1f5f9',
          border: '#e2e8f0',
          primary: '#1d4ed8',
          accent: '#059669',
          warning: '#d97706',
          danger: '#dc2626',
          highlight: '#0284c7',
        },
        // Swiss International Design System
        swiss: {
          bg: '#FFFFFF',
          fg: '#000000',
          muted: '#F2F2F2',
          accent: '#FF3000', // Swiss Red
          border: '#000000',
        },
        // Kinetic Typography Design System
        kinetic: {
          bg: '#09090B', // Rich Black
          fg: '#FAFAFA', // Off-White
          muted: '#27272A', // Dark Gray
          'muted-fg': '#A1A1AA', // Zinc 400
          accent: '#DFE104', // Acid Yellow
          border: '#3F3F46', // Zinc 700
        },
        // Neo-Brutalism Design System
        neo: {
          bg: '#FFFDF5', // Warm Cream
          ink: '#000000', // Pure Black
          accent: '#FF6B6B', // Hot Red
          secondary: '#FFD93D', // Vivid Yellow
          muted: '#C4B5FD', // Soft Violet
        },
        // Botanical / Organic Serif Design System
        botanical: {
          bg: '#F9F8F4', // Warm Alabaster / Rice Paper
          fg: '#2D3A31', // Deep Forest Green
          accent: '#8C9A84', // Sage Green
          muted: '#DCCFC2', // Soft Clay
          interactive: '#C27B66', // Terracotta
          border: '#E6E2DA', // Stone
        },
        // Hand-Drawn Sketch Design System
        sketch: {
          bg: '#fdfbf7', // Warm Paper
          fg: '#2d2d2d', // Soft Pencil Black
          muted: '#e5e0d8', // Old Paper / Erased Pencil
          accent: '#ff4d4d', // Red Correction Marker
          secondary: '#2d5da1', // Blue Ballpoint Pen
          yellow: '#fff9c4', // Post-it Yellow
          paper: '#ffffff', // Bright Paper
        },
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        display: ['"Inter Tight"', 'Inter', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
        space: ['"Space Grotesk"', 'sans-serif'],
        playfair: ['"Playfair Display"', 'Georgia', 'serif'],
        source: ['"Source Sans 3"', 'sans-serif'],
        hand: ['Kalam', 'cursive'],
        handwritten: ['"Patrick Hand"', 'cursive'],
      },
      borderRadius: {
        wobbly: '255px 15px 225px 15px / 15px 225px 15px 255px',
        wobblyMd: '24px 8px 32px 10px / 10px 30px 12px 28px',
      },
      letterSpacing: {
        display: '-0.03em',
        annotation: '0.18em',
      },
      fontSize: {
        'display-xl': ['clamp(3rem, 8vw, 6.5rem)', { lineHeight: '0.98', letterSpacing: '-0.04em' }],
        'display-lg': ['clamp(2.5rem, 5vw, 4.25rem)', { lineHeight: '1.02', letterSpacing: '-0.035em' }],
        'display-md': ['clamp(1.75rem, 3.5vw, 2.75rem)', { lineHeight: '1.08', letterSpacing: '-0.025em' }],
        'display-sm': ['clamp(1.375rem, 2.4vw, 1.75rem)', { lineHeight: '1.12', letterSpacing: '-0.02em' }],
      },
      boxShadow: {
        /* Brutalist hard shadows — zero blur, pure black, always paired with a
           2px black border. These mirror the landing's arbitrary values
           (shadow-[2px_2px_0px_0px_#000] … [8px_8px_0px_0px_#000]) as named
           utilities so the app and the landing cannot drift apart.
           Declared flat, not nested: a nested `brutal: { … }` object reaches
           parseBoxShadowValue as an object and fails the build
           ("input.slice is not a function"). Same shape as `sketch-sm` below. */
        'brutal-sm': '2px 2px 0 0 #000000',
        'brutal': '3px 3px 0 0 #000000',
        'brutal-md': '4px 4px 0 0 #000000',
        'brutal-lg': '6px 6px 0 0 #000000',
        'brutal-xl': '8px 8px 0 0 #000000',
        'subtle': '0 1px 3px 0 rgba(0, 0, 0, 0.05), 0 1px 2px 0 rgba(0, 0, 0, 0.03)',
        'elevated': '0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03)',
        'premium': '0 10px 25px -3px rgba(0, 0, 0, 0.07), 0 4px 6px -2px rgba(0, 0, 0, 0.03)',
        'line': '0 0 0 1px rgba(26,29,35,0.04)',
        // Hand-Drawn Sketch hard-offset (cut-paper) shadows — never use blur
        'sketch': '4px 4px 0px 0px #2d2d2d',
        'sketch-sm': '2px 2px 0px 0px #2d2d2d',
        'sketch-lg': '8px 8px 0px 0px #2d2d2d',
        'sketch-lift': '3px 3px 0px 0px rgba(45, 45, 45, 0.12)',
      },
      keyframes: {
        giggle: {
          '0%, 100%': { transform: 'rotate(-1.5deg)' },
          '50%': { transform: 'rotate(1.5deg)' },
        },
        floaty: {
          '0%, 100%': { transform: 'translateY(0) rotate(-2deg)' },
          '50%': { transform: 'translateY(-10px) rotate(2deg)' },
        },
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        giggle: 'giggle 3s ease-in-out infinite',
        floaty: 'floaty 5s ease-in-out infinite',
        'fade-up': 'fade-up 0.4s ease-out',
      },
    },
  },
  plugins: [],
}
