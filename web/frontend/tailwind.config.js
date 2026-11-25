/** Biên dịch: cd frontend && npx tailwindcss -i src/app.css -o ../public_html/assets/css/app.css --minify */
module.exports = {
  content: ['../app/views/**/*.php', '../public_html/assets/js/app.js', '../public_html/assets/js/admin.js', '../app/src/**/*.php'],
  theme: {
    extend: {
      colors: {
        jade: { 50: '#F4F7F2', 100: '#E9EFE6', 200: '#D5E0D0', 300: '#B5C8AE' },
        ink: { DEFAULT: '#1E2A22', soft: '#46564B', mute: '#6B7A70' },
        tea: { DEFAULT: '#2F5D46', dark: '#234836', light: '#3F7A5C' },
        turmeric: { DEFAULT: '#D9A21B', dark: '#A87A0C', light: '#F6E3AE' },
        coffee: { DEFAULT: '#4A2F24', light: '#7A5443' },
        kraft: { DEFAULT: '#C9A878', light: '#E8D8BC' },
        alert: { DEFAULT: '#B3261E', light: '#F9DEDC' },
      },
      fontFamily: {
        sans: ['"Be Vietnam Pro"', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        // thang chữ tỉ lệ ~1.25
        xs: ['0.8rem', '1.15rem'], sm: ['0.889rem', '1.3rem'], base: ['1rem', '1.6rem'],
        lg: ['1.125rem', '1.7rem'], xl: ['1.333rem', '1.8rem'], '2xl': ['1.777rem', '2.1rem'],
        '3xl': ['2.369rem', '2.6rem'], '4xl': ['3.157rem', '3.3rem'], '5xl': ['4.209rem', '4.2rem'],
      },
      maxWidth: { page: '76rem' },
    },
  },
  plugins: [],
};
