/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        cloud: {
          50: "#f8fbff",
          100: "#eef5ff",
          200: "#d8e8fb",
          300: "#bdd7f8"
        },
        accent: {
          500: "#3b82f6",
          600: "#2563eb",
          700: "#1d4ed8"
        }
      },
      boxShadow: {
        glow: "0 12px 34px rgba(24, 72, 120, 0.10), 0 0 0 1px rgba(132, 164, 207, 0.24)"
      },
      fontFamily: {
        display: ["Sora", "sans-serif"],
        body: ["Manrope", "sans-serif"]
      },
      backgroundImage: {
        "hero-gradient":
          "linear-gradient(180deg, #ffffff 0%, #f8fbff 100%)"
      }
    }
  },
  plugins: []
};
