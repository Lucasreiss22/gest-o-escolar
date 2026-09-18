(function () {
    var sidebar = document.getElementById("sidebar");
    var overlay = document.getElementById("sidebarOverlay");
    var toggle = document.getElementById("menuToggle");

    if (!sidebar) return;

    function closeMenu() {
        sidebar.classList.remove("open");
        if (overlay) overlay.classList.remove("visible");
        document.body.classList.remove("menu-open");
    }

    function openMenu() {
        sidebar.classList.add("open");
        if (overlay) overlay.classList.add("visible");
        document.body.classList.add("menu-open");
    }

    if (toggle) {
        toggle.addEventListener("click", function () {
            if (sidebar.classList.contains("open")) closeMenu();
            else openMenu();
        });
    }

    if (overlay) overlay.addEventListener("click", closeMenu);

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") closeMenu();
    });
})();

(function () {
    function aplicarCamposContrato(escopo) {
        var raiz = escopo || document;
        var seletores = raiz.querySelectorAll("[data-contrato-select]");
        seletores.forEach(function (sel) {
            var tipo = (sel.value || "clt_mensalista").toLowerCase();
            if (tipo === "horista") tipo = "clt_horista";
            if (tipo === "autonomo" || tipo === "extra_pf") tipo = "rpa";
            var form = sel.closest("form") || raiz;
            form.querySelectorAll("[data-contratos]").forEach(function (bloco) {
                var lista = (bloco.getAttribute("data-contratos") || "").split(/\s+/);
                var visivel = lista.indexOf(tipo) !== -1 || lista.indexOf("todos") !== -1;
                bloco.hidden = !visivel;
                bloco.querySelectorAll("input, select, textarea").forEach(function (campo) {
                    if (campo.hasAttribute("data-obrigatorio")) {
                        campo.required = visivel;
                    }
                });
            });
        });
    }

    document.addEventListener("change", function (event) {
        if (event.target && event.target.hasAttribute("data-contrato-select")) {
            aplicarCamposContrato(event.target.form || document);
        }
        if (event.target && event.target.hasAttribute("data-custo-select")) {
            aplicarCamposCusto(event.target.form || document);
        }
    });

    function aplicarCamposCusto(escopo) {
        var raiz = escopo || document;
        raiz.querySelectorAll("[data-custo-select]").forEach(function (sel) {
            var tipo = sel.value || "avista";
            var form = sel.closest("form") || raiz;
            form.querySelectorAll("[data-custos]").forEach(function (bloco) {
                var lista = (bloco.getAttribute("data-custos") || "").split(/\s+/);
                var visivel = lista.indexOf(tipo) !== -1;
                bloco.hidden = !visivel;
                bloco.querySelectorAll("input,select,textarea").forEach(function (el) {
                    el.disabled = !visivel;
                });
            });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            aplicarCamposContrato();
            aplicarCamposCusto();
        });
    } else {
        aplicarCamposContrato();
        aplicarCamposCusto();
    }
})();
