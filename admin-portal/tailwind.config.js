/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        base: "#0B0E11",
        panel: "#12161C",
        panelalt: "#171C24",
        border: "#232A33",
        text: "#E6E9EC",
        muted: "#7C8794",
        accent: "#4FD1FF",
        warn: "#FFB454",
        danger: "#FF6B6B",
        ok: "#57D9A3",
      },
      fontFamily: {
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
        sans: ["Inter", "ui-sans-serif", "system-ui"],
      },
    },
  },
  plugins: [],
}
