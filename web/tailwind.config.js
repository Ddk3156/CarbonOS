/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#07080b",
          900: "#0c0e13",
          800: "#141821",
          700: "#1c2230",
        },
        paper: {
          50: "#f7f1e8",
          100: "#efe6d6",
        },
        ember: {
          300: "#f0c48a",
          400: "#e8a15a",
          500: "#d9893a",
        },
      },
      fontFamily: {
        sans: ['"Segoe UI"', "system-ui", "sans-serif"],
        serif: ["Georgia", '"Iowan Old Style"', "serif"],
      },
      fontSize: {
        xs: ["18px", "1.45"],
        sm: ["18px", "1.45"],
        base: ["18px", "1.45"],
      },
      boxShadow: {
        glass: "0 10px 40px rgba(0,0,0,0.35)",
      },
    },
  },
  plugins: [],
};
