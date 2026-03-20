import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        heading: ["var(--font-bebas-neue)", "system-ui", "sans-serif"],
      },
      boxShadow: {
        neon: "0 0 10px rgba(20,184,166,0.5), 0 0 40px rgba(20,184,166,0.2)",
        "neon-lg":
          "0 0 20px rgba(20,184,166,0.6), 0 0 80px rgba(20,184,166,0.2)",
      },
      animation: {
        "particle-float": "particle-float 10s linear infinite",
        marquee: "marquee 40s linear infinite",
        bounce: "bounce 2s ease-in-out infinite",
      },
      keyframes: {
        "particle-float": {
          "0%": { transform: "translateY(0)", opacity: "1" },
          "100%": { transform: "translateY(-100px)", opacity: "0" },
        },
        marquee: {
          "0%": { transform: "translateX(0)" },
          "100%": { transform: "translateX(-50%)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
