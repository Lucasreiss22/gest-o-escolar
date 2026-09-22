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

    function montarEnderecoTexto(dados, numero) {
        var rua = dados.logradouro || "";
        if (numero) rua = rua ? rua + ", " + numero : numero;
        return [rua, dados.bairro, dados.localidade ? (dados.uf ? dados.localidade + "/" + dados.uf : dados.localidade) : dados.uf, formatarCep(dados.cep)].filter(Boolean).join(" — ");
    }

    function preencherEndereco(form, dados) {
        if (!form || !dados) return;
        function setar(nomes, valor) {
            if (valor === undefined || valor === null || valor === "") return;
            var el = campoForm(form, nomes);
            if (el) el.value = valor;
        }
        setar(["cep"], formatarCep(dados.cep));
        setar(["rua", "logradouro"], dados.logradouro);
        setar(["bairro"], dados.bairro);
        setar(["cidade"], dados.localidade);
        setar(["estado", "estado_uf"], dados.uf);
        if (dados.complemento) setar(["complemento"], dados.complemento);
        var numEl = campoForm(form, ["numero"]);
        var completo = campoForm(form, ["endereco"]);
        if (completo) completo.value = montarEnderecoTexto(dados, numEl ? numEl.value : "");
    }

    function caixaSugestoes(campo) {
        var wrap = (campo && (campo.closest(".endereco-logradouro") || campo.closest("[data-endereco-correios]") || campo.parentElement)) || null;
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

    function partesBusca(form, textoRua) {
        var t = (textoRua || "").trim();
        var cidadeEl = campoForm(form, ["cidade"]);
        var ufEl = campoForm(form, ["estado", "estado_uf"]);
        var localidade = ((cidadeEl && cidadeEl.value) || "").trim();
        var uf = ((ufEl && ufEl.value) || "").trim().toUpperCase();
        var logradouro = t;
        var extra = t.match(/^(.*?)[,\-–]\s*([^,\-–/]+?)[,\-–/\s]+([A-Za-z]{2})\s*$/);
        if (extra) {
            logradouro = extra[1].trim();
            localidade = extra[2].trim();
            uf = extra[3].toUpperCase();
        } else {
            var soCidade = t.match(/^(.*?)[,\-–]\s*([^,\-–]+)\s*$/);
            if (soCidade && uf.length === 2) {
                logradouro = soCidade[1].trim();
                localidade = soCidade[2].trim();
            }
        }
        if (ufEl && uf) ufEl.value = uf;
        return { logradouro: logradouro, localidade: localidade, uf: uf };
    }

    function buscarCep(campo) {
        if (!campo) return;
        if (!campo.hasAttribute("data-cep") && campo.name !== "cep") return;
        var cep = (campo.value || "").replace(/\D/g, "");
        if (cep.length !== 8) return;
        var form = campo.form || campo.closest("form") || document;
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
        var rua = campoForm(form, ["rua", "logradouro"]) || campo;
        var partes = partesBusca(form, (rua && rua.value) || "");
        var box = caixaSugestoes(rua || campo);
        if (partes.uf.length !== 2 || partes.localidade.length < 3 || partes.logradouro.length < 3) {
            if (forcar && box) {
                box.hidden = false;
                box.innerHTML = '<div class="cep-vazio">Informe UF, cidade e pelo menos 3 letras da rua para buscar nos Correios. Ex.: Rua do Imperador, Petrópolis, RJ</div>';
            }
            return;
        }
        var url = "https://viacep.com.br/ws/" + encodeURIComponent(partes.uf) + "/" + encodeURIComponent(partes.localidade) + "/" + encodeURIComponent(partes.logradouro) + "/json/";
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

    function ligarTodosCep() {
        document.querySelectorAll("input[name='cep'], input[data-cep]").forEach(function (el) {
            el.setAttribute("data-cep", "");
            var form = el.form || el.closest("form");
            if (!form) return;
            var rua = campoForm(form, ["rua", "logradouro"]);
            if (rua) rua.setAttribute("data-logradouro", "");
        });
    }

    document.addEventListener("blur", function (event) {
        buscarCep(event.target);
    }, true);
    document.addEventListener("input", function (event) {
        var campo = event.target;
        if (!campo) return;
        if ((campo.hasAttribute("data-cep") || campo.name === "cep") && (campo.value || "").replace(/\D/g, "").length === 8) {
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
        if (campo.name === "cidade" || campo.name === "estado" || campo.name === "estado_uf" || campo.name === "numero") {
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
        if (!event.target.closest(".endereco-logradouro") && !event.target.closest("[data-endereco-correios]")) {
            fecharSugestoes(document);
        }
    });

    document.addEventListener("blur", function (event) {
        var campo = event.target;
        if (!campo || !campo.hasAttribute("data-moeda")) return;
        aplicarMascaraMoeda(campo);
    }, true);

    var NOMES_MOEDA = {
        salario: 1, valor: 1, valor_hora: 1, valor_mensalidade: 1, desconto_valor: 1,
        valor_custo: 1, valor_bruto_custo: 1, valor_hora_extra: 1
    };

    function soDigitos(s) {
        return String(s || "").replace(/\D/g, "");
    }

    function formatarMoedaBR(digitos) {
        var d = String(digitos || "").replace(/^0+/, "");
        if (!d) return "";
        if (d.length === 1) d = "0" + d;
        if (d.length === 2) d = "0" + d;
        var cent = d.slice(-2);
        var inteiro = d.slice(0, -2);
        var grupos = [];
        while (inteiro.length > 3) {
            grupos.unshift(inteiro.slice(-3));
            inteiro = inteiro.slice(0, -3);
        }
        if (inteiro) grupos.unshift(inteiro);
        return grupos.join(".") + "," + cent;
    }

    function aplicarMascaraMoeda(campo) {
        if (!campo) return;
        var bruto = (campo.value || "").trim();
        if (!bruto) {
            campo.value = "";
            return;
        }
        var d = soDigitos(bruto);
        if (!d || parseInt(d, 10) === 0) {
            campo.value = "";
            return;
        }
        if (d.length > 12) d = d.slice(-12);
        campo.value = formatarMoedaBR(d);
    }

    function ligarCamposMoeda() {
        document.querySelectorAll("input").forEach(function (el) {
            var nome = el.getAttribute("name") || "";
            if (NOMES_MOEDA[nome] || el.hasAttribute("data-moeda")) {
                el.setAttribute("data-moeda", "");
                el.setAttribute("inputmode", "numeric");
                if (!el.getAttribute("placeholder")) el.setAttribute("placeholder", "Digite o valor");
                aplicarMascaraMoeda(el);
            }
        });
    }

    document.addEventListener("input", function (event) {
        var campo = event.target;
        if (campo && campo.hasAttribute("data-moeda")) aplicarMascaraMoeda(campo);
    });

    function ligarHoraPickers() {
        document.querySelectorAll("[data-hora-picker]").forEach(function (box) {
            if (box._horaOk) return;
            box._horaOk = true;
            var hidden = box.querySelector("input[type='hidden']");
            var selH = box.querySelector("[data-hora-h]");
            var selM = box.querySelector("[data-hora-m]");
            if (!hidden || !selH || !selM) return;
            function gravar() {
                var h = parseInt(selH.value, 10) || 0;
                var m = parseInt(selM.value, 10) || 0;
                hidden.value = (h + m / 60).toFixed(2);
                box.querySelectorAll("[data-hora-atalho]").forEach(function (btn) {
                    btn.classList.toggle("sel", parseInt(btn.getAttribute("data-hora-atalho"), 10) === h && m === 0);
                });
            }
            selH.addEventListener("change", gravar);
            selM.addEventListener("change", gravar);
            box.addEventListener("click", function (event) {
                var btn = event.target.closest("[data-hora-atalho]");
                if (!btn) return;
                event.preventDefault();
                selH.value = String(parseInt(btn.getAttribute("data-hora-atalho"), 10) || 0);
                selM.value = "0";
                gravar();
            });
            gravar();
        });
    }

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
            ligarTodosCep();
            ligarCamposMoeda();
            ligarHoraPickers();
        });
    } else {
        aplicarCamposContrato();
        aplicarCamposCusto();
        ligarTodosCep();
        ligarCamposMoeda();
        ligarHoraPickers();
    }
})();
