// Standalone ESLint (flat config). `next lint` was removed in Next 16, which
// is why `npm run lint` used to fail with "Invalid project directory".
import coreWebVitals from "eslint-config-next/core-web-vitals";
import typescript from "eslint-config-next/typescript";

const config = [
  ...coreWebVitals,
  ...typescript,
  {
    ignores: [".next/**", "out/**", "node_modules/**", "next-env.d.ts", "coverage/**"],
  },
];

export default config;
