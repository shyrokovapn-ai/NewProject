import js from "@eslint/js";
import prettier from "eslint-config-prettier";
import hooks from "eslint-plugin-react-hooks";
import react from "eslint-plugin-react";
import globals from "globals";

export default [
  { ignores: ["dist"] },
  js.configs.recommended,
  react.configs.flat.recommended,
  react.configs.flat["jsx-runtime"],
  {
    files: ["**/*.{js,jsx}"],
    plugins: { "react-hooks": hooks },
    languageOptions: { globals: globals.browser },
    settings: { react: { version: "18.3" } },
    rules: { ...hooks.configs.recommended.rules, "react/prop-types": "off" },
  },
  prettier,
];
