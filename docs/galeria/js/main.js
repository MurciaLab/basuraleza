document.addEventListener('DOMContentLoaded', function() {
  var grid = document.querySelector('.grid');
  imagesLoaded(grid, function() {
    new Masonry(grid, {
      itemSelector: '.grid-item',
      gutter: 10,
      percentPosition: true
    });
  });
});