// Hidden shop page (PREVIEW). Renders whatever GET /api/shop/products returns (the Worker's src/shop-catalog.js), so a new
// product needs no change here. Copy rules (Grant): no odds, luck, win, bet, worth, value, prize, "limited edition",
// valuable or resale wording; tee design / mockup images only.
(function () {
  var API = "https://api.satoshistatues.workers.dev";
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
  var money = function (cents) { return "$" + (cents % 100 ? (cents / 100).toFixed(2) : String(cents / 100)); };
  var q = new URLSearchParams(location.search);
  if (q.get("ordered")) $("banner").innerHTML = '<div class="shop-banner ok"><strong>Thank you, your order is in.</strong> Each piece is printed to order, so please allow about a week before it ships.</div>';
  else if (q.get("canceled")) $("banner").innerHTML = '<div class="shop-banner info">Checkout was canceled. Nothing was charged.</div>';

  function card(p) {
    var sizes = p.variants.map(function (v, i) {
      return '<label><input type="radio" name="size-' + esc(p.id) + '" value="' + esc(v.key) + '"' + (v.key === "M" || (i === 0 && !p.variants.some(function (x) { return x.key === "M"; })) ? " checked" : "") + '><span>' + esc(v.label) + '</span></label>';
    }).join("");
    var details = (p.details || []).map(function (d) { return "<li>" + esc(d) + "</li>"; }).join("");
    var ships = p.ship_countries && p.ship_countries.length === 1 && p.ship_countries[0] === "US" ? "Ships within the US." : "Ships to " + esc((p.ship_countries || []).join(", ")) + ".";
    return '<article class="item" data-id="' + esc(p.id) + '">' +
      '<div><img src="' + esc(p.mockup) + '" alt="' + esc(p.short_name) + ', front and back" width="1024" height="768" loading="lazy"></div>' +
      '<div><h2>' + esc(p.name) + '</h2>' +
      '<div class="price">' + money(p.price_cents) + ' <small>shipped</small></div>' +
      '<p class="desc">' + esc(p.description) + '</p>' +
      (details ? '<ul class="details">' + details + '</ul>' : "") +
      '<fieldset class="sizes"><legend>Size</legend>' + sizes + '</fieldset>' +
      '<button class="buy" type="button">Buy · ' + money(p.price_cents) + ' shipped</button>' +
      '<div class="err" role="status"></div>' +
      '<p class="fine">' + ships + ' Secure checkout by Stripe. Shipping is included in the price.</p></div></article>';
  }

  function wire(el, p) {
    var btn = el.querySelector(".buy"), err = el.querySelector(".err");
    btn.addEventListener("click", function () {
      var sel = el.querySelector('input[type=radio]:checked');
      if (!sel) { err.textContent = "Pick a size."; return; }
      btn.disabled = true; err.textContent = "";
      fetch(API + "/api/shop/checkout", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ product_id: p.id, variant: sel.value }) })
        .then(function (r) { return r.json().catch(function () { return {}; }); })
        .then(function (j) {
          if (j && j.ok && j.checkout_url) { location.href = j.checkout_url; return; }
          err.textContent = (j && j.message) || "Checkout isn’t available right now."; btn.disabled = false;
        })
        .catch(function () { err.textContent = "Couldn’t reach checkout. Please try again."; btn.disabled = false; });
    });
  }

  fetch(API + "/api/shop/products").then(function (r) { return r.json(); }).then(function (j) {
    var list = (j && j.enabled && j.products) || [];
    if (!list.length) { $("items").innerHTML = '<p class="sub">The shop isn’t open yet. Check back soon.</p>'; return; }
    $("items").innerHTML = list.map(card).join("");
    list.forEach(function (p) { wire(document.querySelector('.item[data-id="' + p.id + '"]'), p); });
  }).catch(function () { $("items").innerHTML = '<p class="sub">The shop isn’t open yet. Check back soon.</p>'; });
})();
