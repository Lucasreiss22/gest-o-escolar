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

    function campoForm(form, nomes) {
        for (var i = 0; i < nomes.length; i++) {
            var el = form.querySelector("[name='" + nomes[i] + "']");
            if (el) return el;
        }
        return null;
    }

    function formatarCep(cep) {
        var d = String(cep || "").replace(/\D/g, "");
        if (d.length === 8) return d.slice(0, 5) + "-" + d.slice(5);
        return String(cep || "");
    }

    function preencherEndereco(form, dados) {
        if (!form || !dados) return;
        function setar(nomes, valor) {
            if (!valor) return;
            var el = campoForm(form, nomes);
            if (el) el.value = valor;
        }
        setar(["cep"], formatarCep(dados.cep));
        setar(["rua", "logradouro"], dados.logradouro);
        setar(["bairro"], dados.bairro);
        setar(["cidade"], dados.localidade);
        setar(["estado", "estado_uf"], dados.uf);
        if (dados.complemento) setar(["complemento"], dados.complemento);
    }

    function caixaSugestoes(campo) {
        var wrap = campo.closest(".endereco-logradouro") || campo.parentElement;
        if (!wrap) return null;
        wrap.classList.add("endereco-logradouro");
        var box = wrap.querySelector(".cep-sugestoes");
        if (!box) {
            box = document.createElement("div");
            box.className = "cep-sugestoes";
            box.hidden = true;
            wrap.appendChild(box);
        }
        return box;
    }

    function fecharSugestoes(form) {
        (form || document).querySelectorAll(".cep-sugestoes").forEach(function (box) {
            box.hidden = true;
            box.innerHTML = "";
        });
    }

    function buscarCep(campo) {
        if (!campo || !campo.hasAttribute("data-cep")) return;
        var cep = (campo.value || "").replace(/\D/g, "");
        if (cep.length !== 8) return;
        var form = campo.form || document;
        campo.value = formatarCep(cep);
        fetch("https://viacep.com.br/ws/" + cep + "/json/")
            .then(function (resp) { return resp.json(); })
            .then(function (dados) {
                if (!dados || dados.erro) return;
                form._buscaLogradouro = true;
                preencherEndereco(form, dados);
                setTimeout(function () { form._buscaLogradouro = false; }, 400);
            })
            .catch(function () {});
    }

    var timerLogradouro = null;

    function buscarLogradouro(campo, forcar) {
        if (!campo) return;
        var form = campo.form || campo.closest("form") || document;
        if (form._buscaLogradouro) return;
        var rua = campoForm(form, ["rua", "logradouro"]);
        var cidade = campoForm(form, ["cidade"]);
        var ufEl = campoForm(form, ["estado", "estado_uf"]);
        var logradouro = ((rua && rua.value) || "").trim();
        var localidade = ((cidade && cidade.value) || "").trim();
        var uf = ((ufEl && ufEl.value) || "").trim().toUpperCase();
        if (ufEl && uf) ufEl.value = uf;
        var box = caixaSugestoes(rua || campo);
        if (uf.length !== 2 || localidade.length < 3 || logradouro.length < 3) {
            if (forcar && box) {
                box.hidden = false;
                box.innerHTML = '<div class="cep-vazio">Informe UF, cidade e pelo menos 3 letras da rua para buscar nos Correios.</div>';
            }
            return;
        }
        var url = "https://viacep.com.br/ws/" + encodeURIComponent(uf) + "/" + encodeURIComponent(localidade) + "/" + encodeURIComponent(logradouro) + "/json/";
        fetch(url)
            .then(function (resp) { return resp.json(); })
            .then(function (lista) {
                if (!box) return;
                if (!Array.isArray(lista) || !lista.length || lista.erro) {
                    box.hidden = false;
                    box.innerHTML = '<div class="cep-vazio">Nenhum logradouro encontrado nos Correios. Confira UF, cidade e o nome da rua.</div>';
                    return;
                }
                box.innerHTML = "";
                lista.slice(0, 12).forEach(function (item) {
                    var btn = document.createElement("button");
                    btn.type = "button";
                    btn.textContent = (item.logradouro || "") + " — " + (item.bairro || "") + " · " + formatarCep(item.cep);
                    btn.addEventListener("click", function () {
                        form._buscaLogradouro = true;
                        preencherEndereco(form, item);
                        fecharSugestoes(form);
                        setTimeout(function () { form._buscaLogradouro = false; }, 400);
                    });
                    box.appendChild(btn);
                });
                box.hidden = false;
            })
            .catch(function () {
                if (!box) return;
                box.hidden = false;
                box.innerHTML = '<div class="cep-vazio">Não foi possível consultar os Correios agora.</div>';
            });
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
        if (campo.name === "estado" || campo.name === "estado_uf") {
            campo.value = (campo.value || "").toUpperCase();
        }
        if (campo.hasAttribute("data-logradouro") || campo.name === "rua" || campo.name === "logradouro") {
            clearTimeout(timerLogradouro);
            timerLogradouro = setTimeout(function () {
                buscarLogradouro(campo, false);
            }, 450);
        }
        if (campo.name === "cidade" || campo.name === "estado" || campo.name === "estado_uf") {
            clearTimeout(timerLogradouro);
            timerLogradouro = setTimeout(function () {
                var form = campo.form || document;
                var rua = campoForm(form, ["rua", "logradouro"]);
                if (rua && (rua.value || "").trim().length >= 3) buscarLogradouro(rua, false);
            }, 450);
        }
    });
    document.addEventListener("click", function (event) {
        var botao = event.target.closest("[data-buscar-logradouro]");
        if (botao) {
            event.preventDefault();
            var form = botao.form || botao.closest("form") || document;
            var rua = campoForm(form, ["rua", "logradouro"]);
            buscarLogradouro(rua || botao, true);
            return;
        }
        if (!event.target.closest(".endereco-logradouro")) {
            fecharSugestoes(document);
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

    document.addEventListener("change", function (event) {
        var input = event.target;
        if (!input || input.type !== "file") return;
        var widget = input.closest("[data-foto-preview]");
        if (!widget) return;
        var arquivo = input.files && input.files[0];
        var img = widget.querySelector(".foto-circulo-img");
        var ph = widget.querySelector(".foto-circulo-placeholder");
        if (!arquivo) return;
        if (!arquivo.type || arquivo.type.indexOf("image/") !== 0) return;
        var url = URL.createObjectURL(arquivo);
        if (img) {
            img.src = url;
            img.hidden = false;
        }
        if (ph) ph.hidden = true;
    });

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
