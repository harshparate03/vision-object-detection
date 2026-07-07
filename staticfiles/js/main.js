// // document.addEventListener('DOMContentLoaded', () => {
// //     const lightButton = document.getElementById('light-theme');
// //     const darkButton = document.getElementById('dark-theme');
// //     const body = document.body;
// //     localStorage.setItem('chatenai-theme', 'light');
// //     // Load the theme from localStorage
// //     const savedTheme = localStorage.getItem('chatenai-theme') || 'light';
// //     body.setAttribute('data-theme', savedTheme);
  
// //     if (savedTheme === 'dark') {
// //       body.classList.add('active-light-mode');
// //     } else {
// //       body.classList.remove('active-light-mode');
// //     }
// //     // Event listeners for theme toggles
// //     lightButton.addEventListener('click', () => {
// //       body.classList.remove('active-light-mode');
// //       localStorage.setItem('chatenai-theme', 'light');
// //     //   body.setAttribute('data-theme', 'light');
// //     });
  
// //     darkButton.addEventListener('click', () => {
// //       body.classList.add('active-light-mode');
// //       localStorage.setItem('chatenai-theme', 'dark');
// //     //   body.setAttribute('data-theme', 'dark');
// //     });
// //   });
  

// document.addEventListener('DOMContentLoaded', () => {
//     const lightButton = document.getElementById('light-theme');
//     const darkButton = document.getElementById('dark-theme');
//     const body = document.body;
  
//     // Load theme from localStorage or default to 'light'
//     const savedTheme = localStorage.getItem('chatenai-theme') || 'light';
//     applyTheme(savedTheme);
//     toggleButtonVisibility(savedTheme);
  
//     // Event listeners for theme toggle
//     lightButton.addEventListener('click', () => {
//       const theme = 'light';
//       localStorage.setItem('chatenai-theme', theme);
//       applyTheme(theme);
//       toggleButtonVisibility(theme);
//     });
  
//     darkButton.addEventListener('click', () => {
//       const theme = 'dark';
//       localStorage.setItem('chatenai-theme', theme);
//       applyTheme(theme);
//       toggleButtonVisibility(theme);
//     });
  
//     // Function to apply theme styles
//     function applyTheme(theme) {
//       if (theme === 'dark') {
//         body.classList.add('active-light-mode');
//       } else {
//         body.classList.remove('active-light-mode');
//       }
//     }
  
//     // Function to toggle button visibility
//     function toggleButtonVisibility(theme) {
//       if (theme === 'light') {
//         lightButton.style.display = 'none';
//         darkButton.style.display = 'block';
//       } else {
//         lightButton.style.display = 'block';
//         darkButton.style.display = 'none';
//       }
//     }
//   });
  