// Immediately apply the theme based on localStorage

(function() {
    const darkMode = localStorage.getItem('darkMode');
    const themeClass = darkMode === 'enabled' ? 'dark' : 'light';

    // Apply the theme class to the document immediately
    document.documentElement.className = themeClass;

    // Wait for DOMContentLoaded to set up event listeners
    document.addEventListener('DOMContentLoaded', () => {
        const darkModeToggle = document.getElementById('dark-mode-toggle');
        const lightModeToggle = document.getElementById('light-mode-toggle');

        const toggleMode = (isDarkMode) => {
            document.documentElement.classList.toggle('dark', isDarkMode);
            localStorage.setItem('darkMode', isDarkMode ? 'enabled' : 'disabled');
            updateToggleButtons(isDarkMode);
        };

        const updateToggleButtons = (isDarkMode) => {
            if (isDarkMode) {
                darkModeToggle.classList.remove('activate');
                lightModeToggle.classList.add('activate');
            } else {
                lightModeToggle.classList.remove('activate');
                darkModeToggle.classList.add('activate');
            }
        };

        // Initial activation based on current theme
        updateToggleButtons(themeClass === 'dark');

        // Add event listeners if elements are present
        if (darkModeToggle && lightModeToggle) {
            darkModeToggle.addEventListener('click', () => toggleMode(true));
            lightModeToggle.addEventListener('click', () => toggleMode(false));
        }
    });
})();
