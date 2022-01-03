let flashDiv = document.querySelector('.msg-container');
let closeButton = document.querySelector('.close-button');
let menuLinks = document.querySelector('.main-menu-links');

closeButton.addEventListener('click', () => {
    flashDiv.remove();
});

function hide() {
    if(menuLinks.style.display == 'block') {
        menuLinks.style.display = 'none';
    } else {
        menuLinks.style.display = 'block'
    }
}
