export default [
  {
    files: ['static/**/*.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'script',
      globals: {
        document: 'readonly',
        window: 'readonly',
        Audio: 'readonly',
        MediaMetadata: 'readonly',
        localStorage: 'readonly',
        navigator: 'readonly',
        SpeechSynthesisUtterance: 'readonly',
        fetch: 'readonly',
        URLSearchParams: 'readonly',
        console: 'readonly',
      },
    },
    rules: {
      'no-undef': 'error',
    },
  },
];
