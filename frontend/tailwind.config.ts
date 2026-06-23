import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    container: {
      center: true,
      padding: { DEFAULT: '1rem', sm: '1.5rem', lg: '2rem', xl: '2.5rem' },
      screens: { sm: '640px', md: '768px', lg: '1024px', xl: '1200px', '2xl': '1320px' },
    },
    extend: {
      fontFamily: {
        sans: ['var(--font-vazir)', 'Vazirmatn', 'Tahoma', 'sans-serif'],
        display: ['var(--font-vazir)', 'Vazirmatn', 'Tahoma', 'sans-serif'],
      },
      colors: {
        // Brand palette — eyedropped from graphic designer's mockup
        brand: {
          50:  '#E6F3F1',
          100: '#C2E0DB',
          200: '#92CABF',
          300: '#5DB3A4',
          400: '#2FA08D',
          500: '#0D8074', // primary teal — matches activities panel
          600: '#0A6E64', // header/footer teal
          700: '#085C54',
          800: '#064A43',
          900: '#053832',
          950: '#022721',
        },
        // brighter cyan-teal used in "+ جدید" CTA buttons in design
        mint: {
          50:  '#E6F8F6',
          100: '#C5EFEB',
          400: '#3FD0C2',
          500: '#25C5BA',
          600: '#1FB3A8',
          700: '#178C84',
        },
        accent: {
          50:  '#FFF1E6',
          100: '#FFDCB8',
          200: '#FFC085',
          300: '#FFA552',
          400: '#FF8C2E',
          500: '#FF6B1A', // bright orange used for "مشارکت در مجازات" pill
          600: '#E55214',
          700: '#B83E0F',
          800: '#8A2D0A',
          900: '#5C1E07',
        },
        // golden yellow trophy CTA card
        gold: {
          400: '#FFC44D',
          500: '#FFB033',
          600: '#F0941A',
          700: '#C77815',
        },
        ink: {
          50:  '#F7F8FA',
          100: '#EEF1F4',
          200: '#D9DEE5',
          300: '#B7C0CC',
          400: '#8B95A6',
          500: '#5E6878',
          600: '#414A5A',
          700: '#2E3644',
          800: '#1C2230',
          900: '#0F1420',
        },
        success: '#16A06B',
        warning: '#F59E0B',
        danger:  '#DC2626',
        info:    '#2563EB',
        surface: {
          DEFAULT: '#FFFFFF',
          muted: '#F4F7F8',
          deep: '#0B3530',
        },
      },
      borderRadius: {
        sm: '0.5rem',
        DEFAULT: '0.75rem',
        md: '1rem',
        lg: '1.25rem',
        xl: '1.5rem',
        '2xl': '2rem',
        '3xl': '2.5rem',
      },
      boxShadow: {
        soft: '0 4px 24px -6px rgba(11, 53, 48, 0.08)',
        card: '0 8px 32px -8px rgba(11, 53, 48, 0.10)',
        float: '0 20px 50px -20px rgba(11, 53, 48, 0.30)',
        glow: '0 0 40px -4px rgba(31, 138, 122, 0.45)',
      },
      backgroundImage: {
        'grid-pattern': "url(\"data:image/svg+xml,%3Csvg width='40' height='40' viewBox='0 0 40 40' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M40 0H0v40' fill='none' stroke='%231F8A7A' stroke-opacity='0.06' stroke-width='1'/%3E%3C/svg%3E\")",
        'noise': "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0.18 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")",
      },
      keyframes: {
        'fade-in-up': {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'float': {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-8px)' },
        },
        'shimmer': {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        'pulse-ring': {
          '0%': { transform: 'scale(0.8)', opacity: '0.8' },
          '100%': { transform: 'scale(2)', opacity: '0' },
        },
      },
      animation: {
        'fade-in-up': 'fade-in-up 0.6s ease-out both',
        'float': 'float 6s ease-in-out infinite',
        'shimmer': 'shimmer 2.5s linear infinite',
        'pulse-ring': 'pulse-ring 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
};

export default config;
