document.addEventListener("submit", function (e) {
  var msg = e.target.getAttribute("data-confirm");
  if (msg && !window.confirm(msg)) e.preventDefault();
});
var kind = document.getElementById("kind-filter");
var target = document.getElementById("delivery-select");
if (kind && target) {
  var apply = function () {
    Array.prototype.forEach.call(target.options, function (o) {
      var hide = kind.value && o.getAttribute("data-kind") !== kind.value;
      o.hidden = hide; o.disabled = hide;
    });
    if (target.selectedOptions[0] && target.selectedOptions[0].disabled) target.selectedIndex = -1;
  };
  kind.addEventListener("change", apply); apply();
}

var preview = document.getElementById("stego-preview");
if (preview && target) {
  target.addEventListener("change", function () {
    if (!target.value) { preview.classList.add("hidden"); return; }
    preview.src = preview.getAttribute("data-url").replace("__ID__", target.value);
    preview.classList.remove("hidden");
  });
}
