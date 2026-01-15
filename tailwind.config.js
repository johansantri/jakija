import typography from '@tailwindcss/typography'

export default {
  content: [
    './templates/**/*.html',
    './**/templates/**/*.html',
    './static/**/*.js',
  ],
  theme: {
    extend: {},
  },
  plugins: [
    typography,
  ],
}
