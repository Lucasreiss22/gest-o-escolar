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

    function buscarCep(campo) {
        if (!campo || !campo.hasAttribute("data-cep")) return;
        var cep = (campo.value || "").replace(/\D/g, "");
        if (cep.length !== 8) return;
        var form = campo.form || document;
        fetch("https://viacep.com.br/ws/" + cep + "/json/")
            .then(function (resp) { return resp.json(); })
            .then(function (dados) {
                if (!dados || dados.erro) return;
                function preencher(nome, valor) {
                    var el = form.querySelector("[name='" + nome + "']");
                    if (el && valor) el.value = valor;
                }
                preencher("rua", dados.logradouro);
                preencher("logradouro", dados.logradouro);
                preencher("bairro", dados.bairro);
                preencher("cidade", dados.localidade);
                preencher("estado", dados.uf);
                preencher("estado_uf", dados.uf);
            })
            .catch(function () {});
    }

    document.addEventListener("blur", function (event) {
        buscarCep(event.target);
    }, true);
    document.addEventListener("input", function (event) {
        var campo = event.target;
        if (!campo) return;
        if (campo.hasAttribute("data-cep") && (campo.value || "").replace(/\D/g, "").length === 8) {
            buscarCep(campo);
        }
    });

    document.addEventListener("blur", function (event) {
        var campo = event.target;
        if (!campo || !campo.hasAttribute("data-moeda")) return;
        var bruto = (campo.value || "").trim();
        if (!bruto) {
            campo.value = "0.00";
            return;
        }
        var s = bruto.replace("R$", "").replace(/\s/g, "");
        if (s.indexOf(",") >= 0) s = s.replace(/\./g, "").replace(",", ".");
        var n = parseFloat(s);
        if (isNaN(n)) {
            campo.value = bruto;
            return;
        }
        campo.value = n.toFixed(2);
    }, true);

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
