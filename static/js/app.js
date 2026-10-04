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
        setar(["codigo_municipio"], dados.ibge);
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
        salario: 1, valor: 1, valor_hora: 1, valor_mensalidade: 1,
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

    /* Desconto do aluno: percentual é número de 0 a 100 (10 = 10%); só o valor fixo usa a máscara de reais. */
    function numeroBR(texto) {
        var s = String(texto || "").replace(/R\$|\s/g, "");
        if (s.indexOf(",") >= 0) s = s.replace(/\./g, "").replace(",", ".");
        var n = parseFloat(s);
        return isNaN(n) ? 0 : n;
    }

    function moedaBR(n) {
        return "R$ " + n.toFixed(2).replace(".", ",").replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    }

    function textoPercentual(texto) {
        var n = numeroBR(texto);
        if (!n) return "";
        return String(Math.round(Math.min(n, 100) * 100) / 100).replace(".", ",");
    }

    function previaDesconto(form) {
        var tipo = form.querySelector("select[name='desconto_tipo']");
        var campo = form.querySelector("input[name='desconto_valor']");
        var dica = form.querySelector("[data-desconto-dica]");
        var base = form.querySelector("input[name='valor_mensalidade']");
        if (!tipo || !campo || !dica) return;
        var bruto = base ? numeroBR(base.value) : 0;
        var desconto = numeroBR(campo.value);
        var t = tipo.value;
        var liquido = bruto;
        var aviso = "";
        if (t === "percentual") {
            liquido = bruto * (1 - Math.min(desconto, 100) / 100);
            if (desconto > 0 && desconto <= 1) aviso = " Atenção: isso é " + textoPercentual(campo.value) + "% (menos de 1%). Para 10%, digite 10.";
        } else if (t === "valor_fixo") {
            liquido = Math.max(bruto - desconto, 0);
        } else if (t === "bolsa") {
            liquido = 0;
        }
        var texto = t === "percentual" ? "Digite o percentual de 0 a 100 (10 = 10%)." : (t === "valor_fixo" ? "Valor em reais descontado por mês." : "");
        if (bruto > 0 && t !== "nenhum") texto += " Mensalidade: " + moedaBR(bruto) + " → " + moedaBR(Math.round(liquido * 100) / 100) + ".";
        dica.textContent = (texto + aviso).trim();
        dica.classList.toggle("text-danger", !!aviso);
        dica.classList.toggle("text-muted", !aviso);
    }

    function ajustarCampoDesconto(form) {
        if (!form) return;
        var tipo = form.querySelector("select[name='desconto_tipo']");
        var campo = form.querySelector("input[name='desconto_valor']");
        if (!tipo || !campo) return;
        var t = tipo.value;
        if (t === "valor_fixo") {
            if (!campo.hasAttribute("data-moeda")) {
                var v = String(campo.value || "").trim();
                if (v && v.indexOf(",") < 0) campo.value = v + ",00";
                campo.setAttribute("data-moeda", "");
                aplicarMascaraMoeda(campo);
            }
            campo.setAttribute("inputmode", "numeric");
            campo.placeholder = "R$ por mês";
        } else {
            if (campo.hasAttribute("data-moeda")) {
                campo.removeAttribute("data-moeda");
                campo.value = textoPercentual(campo.value);
            }
            campo.setAttribute("inputmode", "decimal");
            campo.placeholder = t === "percentual" ? "Ex.: 10 (= 10%)" : "";
        }
        campo.readOnly = t === "nenhum" || t === "bolsa";
        if (campo.readOnly) campo.value = "";
        previaDesconto(form);
    }

    function ligarCamposDesconto() {
        document.querySelectorAll("select[name='desconto_tipo']").forEach(function (sel) {
            ajustarCampoDesconto(sel.form);
        });
    }

    document.addEventListener("change", function (event) {
        if (event.target && event.target.name === "desconto_tipo") ajustarCampoDesconto(event.target.form);
    });

    document.addEventListener("input", function (event) {
        var campo = event.target;
        if (!campo || !campo.form || !campo.form.querySelector("select[name='desconto_tipo']")) return;
        if (campo.name === "desconto_valor" && !campo.hasAttribute("data-moeda")) {
            var limpo = campo.value.replace(/[^\d,\.]/g, "").replace(".", ",");
            var partes = limpo.split(",");
            if (partes.length > 2) limpo = partes[0] + "," + partes.slice(1).join("");
            if (numeroBR(limpo) > 100) limpo = "100";
            if (limpo !== campo.value) campo.value = limpo;
        }
        if (campo.name === "desconto_valor" || campo.name === "valor_mensalidade") previaDesconto(campo.form);
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
            }
            selH.addEventListener("change", gravar);
            selM.addEventListener("change", gravar);
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

    function limparRotulo(texto) {
        return String(texto || "").replace(/\*/g, "").replace(/\s+/g, " ").trim();
    }

    function rotuloCampo(campo) {
        var aria = campo.getAttribute("aria-label");
        if (aria) return limparRotulo(aria);
        if (campo.id && window.CSS && CSS.escape) {
            var porFor = document.querySelector('label[for="' + CSS.escape(campo.id) + '"]');
            if (porFor) return limparRotulo(porFor.textContent);
        }
        var irmao = campo.previousElementSibling;
        while (irmao) {
            if (irmao.tagName === "LABEL") return limparRotulo(irmao.textContent);
            irmao = irmao.previousElementSibling;
        }
        var nodo = campo.parentElement;
        for (var i = 0; i < 4 && nodo; i++) {
            if (nodo.tagName === "LABEL") return limparRotulo(nodo.textContent);
            var filhos = nodo.children || [];
            for (var j = 0; j < filhos.length; j++) {
                if (filhos[j].tagName === "LABEL") return limparRotulo(filhos[j].textContent);
            }
            nodo = nodo.parentElement;
        }
        var placeholder = campo.getAttribute("placeholder");
        if (placeholder && placeholder !== "Digite o valor") return limparRotulo(placeholder);
        var nome = (campo.getAttribute("name") || "campo").replace(/[_-]+/g, " ");
        return nome.charAt(0).toUpperCase() + nome.slice(1);
    }

    function abaDoCampo(campo) {
        var pane = campo.closest(".tab-pane");
        if (!pane || !pane.id) return "";
        var botao = document.querySelector('[data-bs-target="#' + pane.id + '"]');
        if (!botao) return "";
        return limparRotulo(botao.textContent).replace(/^\d+\.\s*/, "");
    }

    function revelarCampo(campo) {
        var pane = campo.closest(".tab-pane");
        if (pane && pane.id && !pane.classList.contains("show")) {
            var conteudo = pane.parentElement;
            if (conteudo) {
                conteudo.querySelectorAll(".tab-pane").forEach(function (item) {
                    item.classList.remove("show", "active");
                });
            }
            pane.classList.add("show", "active");
            var botao = document.querySelector('[data-bs-target="#' + pane.id + '"]');
            if (botao) {
                var lista = botao.closest(".nav");
                if (lista) {
                    lista.querySelectorAll(".nav-link").forEach(function (item) {
                        item.classList.remove("active");
                        item.setAttribute("aria-selected", "false");
                    });
                }
                botao.classList.add("active");
                botao.setAttribute("aria-selected", "true");
            }
        }
        var detalhes = campo.closest("details");
        if (detalhes) detalhes.open = true;
    }

    function problemaCampo(campo, radios) {
        if (!campo || campo.disabled || campo.type === "hidden" || campo.type === "button" || campo.type === "submit") return "";
        if (campo.type === "radio") {
            if (radios[campo.name]) return "";
            radios[campo.name] = true;
            if (!campo.required) return "";
            var marcado = campo.form && campo.form.querySelector('input[type="radio"][name="' + campo.name + '"]:checked');
            return marcado ? "" : "vazio";
        }
        var vazio = campo.type === "checkbox" ? !campo.checked
            : campo.type === "file" ? !(campo.files && campo.files.length)
            : String(campo.value || "").trim() === "";
        if (campo.required && vazio) return "vazio";
        if (!vazio && campo.type === "email" && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(campo.value).trim())) return "email";
        if (!vazio && campo.minLength > 0 && String(campo.value).length < campo.minLength) return "curto";
        return "";
    }

    function campoForaDeUso(campo) {
        var nodo = campo.parentElement;
        while (nodo && nodo !== document.body) {
            if (nodo.hasAttribute && nodo.hasAttribute("hidden")) return true;
            nodo = nodo.parentElement;
        }
        return false;
    }

    function camposInvalidos(form) {
        var lista = [];
        var radios = {};
        Array.prototype.forEach.call(form.elements || [], function (campo) {
            if (!campo || !campo.tagName) return;
            var tag = campo.tagName;
            if (tag !== "INPUT" && tag !== "SELECT" && tag !== "TEXTAREA") return;
            if (campoForaDeUso(campo)) return;
            var tipo = problemaCampo(campo, radios);
            if (!tipo) return;
            campo._problema = tipo;
            lista.push(campo);
        });
        return lista;
    }

    function textoSeguro(valor) {
        return String(valor || "").replace(/[&<>]/g, function (ch) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;" }[ch];
        });
    }

    function telaEstreita() {
        return window.matchMedia("(max-width: 960px)").matches;
    }

    function avisoAtual(form) {
        var box = document.querySelector(".aviso-campos");
        if (!box) return null;
        return !form || box._form === form ? box : null;
    }

    function posicionarAviso(form, box) {
        box._form = form;
        document.body.appendChild(box);
        box.classList.add("aviso-campos-fixo");
    }

    function ajustarAvisoAoTeclado() {
        var box = document.querySelector(".aviso-campos.aviso-campos-fixo");
        if (!box || box.hidden) return;
        var vista = window.visualViewport;
        if (!vista) {
            box.style.bottom = "";
            return;
        }
        var coberto = Math.max(0, window.innerHeight - vista.height - vista.offsetTop);
        box.style.bottom = (coberto + 12) + "px";
    }

    function irParaCampo(campo) {
        if (!campo) return;
        revelarCampo(campo);
        if (campo.scrollIntoView) campo.scrollIntoView({ block: "center", behavior: "smooth" });
        if (campo.focus) campo.focus();
    }

    function mostrarAviso(form, campos) {
        var box = document.querySelector(".aviso-campos");
        if (!box) {
            box = document.createElement("div");
            box.className = "aviso-campos";
            box.setAttribute("role", "alert");
        }
        box._campos = campos;
        posicionarAviso(form, box);
        var itens = campos.map(function (campo, indice) {
            var aba = abaDoCampo(campo);
            var extra = campo._problema === "email" ? "Formato inválido" : (campo._problema === "curto" ? "Curto demais" : "");
            return "<button type=\"button\" class=\"aviso-ir\" data-idx=\"" + indice + "\">" +
                "<span class=\"aviso-nome\">" + textoSeguro(rotuloCampo(campo)) + "</span>" +
                (aba ? "<span class=\"aviso-aba\">Aba " + textoSeguro(aba) + "</span>" : "") +
                (extra ? "<span class=\"aviso-extra\">" + extra + "</span>" : "") +
                "</button>";
        });
        box.innerHTML = "<div class=\"aviso-cabeca\"><strong>Falta preencher</strong>" +
            "<button type=\"button\" class=\"aviso-fechar\" aria-label=\"Fechar aviso\">×</button></div>" +
            "<p class=\"aviso-dica\">Escolha o campo para ir até ele.</p>" +
            "<div class=\"aviso-lista\">" + itens.join("") + "</div>";
        box.hidden = false;
        ajustarAvisoAoTeclado();
    }

    function avisarCampos(form) {
        var faltando = camposInvalidos(form);
        form.querySelectorAll(".campo-faltando").forEach(function (item) {
            item.classList.remove("campo-faltando");
        });
        if (!faltando.length) {
            var aviso = avisoAtual(form);
            if (aviso) aviso.hidden = true;
            return true;
        }
        faltando.forEach(function (item) { item.classList.add("campo-faltando"); });
        mostrarAviso(form, faltando);
        if (!telaEstreita()) irParaCampo(faltando[0]);
        return false;
    }

    function prepararFormularios() {
        document.querySelectorAll("form").forEach(function (form) {
            form.setAttribute("novalidate", "novalidate");
        });
    }

    document.addEventListener("click", function (event) {
        var fechar = event.target.closest && event.target.closest(".aviso-fechar");
        if (fechar) {
            var caixa = fechar.closest(".aviso-campos");
            if (caixa) caixa.hidden = true;
            return;
        }
        var botao = event.target.closest && event.target.closest(".aviso-ir");
        if (!botao) return;
        var box = botao.closest(".aviso-campos");
        var indice = Number(botao.getAttribute("data-idx"));
        if (!box || !box._campos || !box._campos[indice]) return;
        irParaCampo(box._campos[indice]);
    });

    if (window.visualViewport) {
        window.visualViewport.addEventListener("resize", ajustarAvisoAoTeclado);
        window.visualViewport.addEventListener("scroll", ajustarAvisoAoTeclado);
    }

    document.addEventListener("submit", function (event) {
        var form = event.target;
        if (!form || form.tagName !== "FORM") return;
        if (!avisarCampos(form)) {
            event.preventDefault();
            event.stopPropagation();
        }
    }, true);

    document.addEventListener("submit", function (event) {
        var form = event.target;
        if (!form || form.tagName !== "FORM" || event.defaultPrevented) return;
        var metodo = (form.getAttribute("method") || "get").toLowerCase();
        if (metodo !== "post" || form.target || form.hasAttribute("data-permitir-reenvio")) return;
        var agora = Date.now();
        var ultimo = Number(form.dataset.enviadoEm || 0);
        if (ultimo && agora - ultimo < 6000) {
            event.preventDefault();
            event.stopPropagation();
            return;
        }
        form.dataset.enviadoEm = String(agora);
        form.classList.add("form-enviando");
        setTimeout(function () {
            form.classList.remove("form-enviando");
        }, 6000);
    });

    window.addEventListener("pageshow", function () {
        document.querySelectorAll("form.form-enviando").forEach(function (form) {
            form.classList.remove("form-enviando");
            delete form.dataset.enviadoEm;
        });
    });

    document.addEventListener("input", function (event) {
        var campo = event.target;
        if (campo && campo.setCustomValidity) campo.setCustomValidity("");
        if (campo && campo.classList) campo.classList.remove("campo-faltando");
    }, true);

    document.addEventListener("change", function (event) {
        var campo = event.target;
        if (campo && campo.setCustomValidity) campo.setCustomValidity("");
        if (campo && campo.classList) campo.classList.remove("campo-faltando");
    }, true);

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            prepararFormularios();
            aplicarCamposContrato();
            aplicarCamposCusto();
            ligarTodosCep();
            ligarCamposMoeda();
            ligarCamposDesconto();
            ligarHoraPickers();
        });
    } else {
        prepararFormularios();
        aplicarCamposContrato();
        aplicarCamposCusto();
        ligarTodosCep();
        ligarCamposMoeda();
        ligarCamposDesconto();
        ligarHoraPickers();
    }
})();

/* Enter nos campos passa para o próximo campo em vez de enviar o formulário.
   No último campo, o foco vai para o botão de salvar (Enter de novo envia).
   Senha e o último campo de formulários de busca (GET) continuam enviando.
   Para manter o envio direto num formulário ou campo, use data-enter-envia. */
(function () {
    var TIPOS_IGNORADOS = /^(button|submit|reset|image|file|hidden)$/i;

    function visivel(el) {
        if (!el || el.disabled || el.hidden) return false;
        if (el.closest && el.closest("[hidden], [inert]")) return false;
        if (el.getAttribute("tabindex") === "-1") return false;
        return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
    }

    function navegaveis(form) {
        return Array.prototype.filter.call(form.elements, function (el) {
            var tag = el.tagName;
            if (tag === "FIELDSET" || tag === "OBJECT" || tag === "OUTPUT" || tag === "BUTTON") return false;
            if (tag === "INPUT" && TIPOS_IGNORADOS.test(el.type)) return false;
            if (el.readOnly && tag !== "SELECT") return false;
            return visivel(el);
        });
    }

    function botaoEnviar(form) {
        var botoes = Array.prototype.filter.call(form.elements, function (el) {
            if (el.tagName === "BUTTON") return (el.getAttribute("type") || "submit").toLowerCase() === "submit" && visivel(el);
            return el.tagName === "INPUT" && /^(submit|image)$/i.test(el.type) && visivel(el);
        });
        return botoes[0] || null;
    }

    function focar(el) {
        el.focus();
        if (el.scrollIntoView) el.scrollIntoView({ block: "nearest" });
        if (el.tagName === "INPUT" && el.select && /^(text|search|email|tel|url|number)$/i.test(el.type)) {
            try { el.select(); } catch (e) { /* number em alguns navegadores */ }
        }
    }

    document.addEventListener("keydown", function (event) {
        if (event.key !== "Enter" || event.defaultPrevented || event.isComposing) return;
        if (event.ctrlKey || event.altKey || event.metaKey || event.shiftKey) return;
        var campo = event.target;
        if (!campo || (campo.tagName !== "INPUT" && campo.tagName !== "SELECT")) return;
        if (campo.tagName === "INPUT" && TIPOS_IGNORADOS.test(campo.type)) return;
        var form = campo.form;
        if (!form) return;
        if (campo.closest("[data-enter-envia]") || form.hasAttribute("data-enter-envia")) return;
        if (campo.type === "password") return;

        var lista = navegaveis(form);
        var pos = lista.indexOf(campo);
        var proximo = pos >= 0 ? lista[pos + 1] : null;
        if (proximo) {
            event.preventDefault();
            focar(proximo);
            return;
        }
        if ((form.getAttribute("method") || "get").toLowerCase() === "get") return;
        event.preventDefault();
        var botao = botaoEnviar(form);
        if (botao) focar(botao);
    });
})();

/* Caixa "horário marcado": mostra e exige o campo de hora indicado em data-horario-marcado. */
(function () {
    function aplicar(caixa, focar) {
        var alvo = document.getElementById(caixa.getAttribute("data-horario-marcado"));
        if (!alvo) return;
        alvo.hidden = !caixa.checked;
        alvo.required = caixa.checked;
        if (!caixa.checked) alvo.value = "";
        else if (focar) alvo.focus();
    }

    document.addEventListener("change", function (event) {
        var caixa = event.target;
        if (caixa && caixa.matches && caixa.matches("[data-horario-marcado]")) aplicar(caixa, true);
    });

    function iniciar() {
        document.querySelectorAll("[data-horario-marcado]").forEach(function (caixa) { aplicar(caixa, false); });
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar);
    else iniciar();
})();

/* Valor da hora extra: "clt" esconde o campo de valor fixo; "fixo" mostra. */
(function () {
    function aplicar(seletor, focar) {
        var form = seletor.form || document;
        var fixo = seletor.value === "fixo";
        form.querySelectorAll("[data-he-fixo]").forEach(function (bloco) {
            bloco.hidden = !fixo;
            var campo = bloco.querySelector("input[name='valor_hora_extra']");
            if (campo && fixo && focar) campo.focus();
        });
        form.querySelectorAll("[data-he-clt]").forEach(function (bloco) { bloco.hidden = fixo; });
    }

    document.addEventListener("change", function (event) {
        var alvo = event.target;
        if (alvo && alvo.matches && alvo.matches("[data-modo-he]")) aplicar(alvo, true);
    });

    function iniciar() {
        document.querySelectorAll("[data-modo-he]").forEach(function (seletor) { aplicar(seletor, false); });
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", iniciar);
    else iniciar();
})();

/* Campo obrigatório numa aba escondida: abre a aba e mostra o aviso no campo. */
(function () {
    var tratando = false;
    document.addEventListener("invalid", function (event) {
        var campo = event.target;
        if (tratando || !campo || !campo.closest) return;
        tratando = true;
        var aba = campo.closest(".tab-pane");
        var botao = aba && aba.id && !aba.classList.contains("active") && window.bootstrap
            ? document.querySelector('[data-bs-target="#' + aba.id + '"], [href="#' + aba.id + '"]')
            : null;
        if (!botao) {
            setTimeout(function () { tratando = false; }, 0);
            return;
        }
        window.bootstrap.Tab.getOrCreateInstance(botao).show();
        setTimeout(function () {
            tratando = false;
            campo.focus();
            if (campo.reportValidity) campo.reportValidity();
        }, 200);
    }, true);
})();

/* Snapshot dos valores iniciais do formulário → auditoria "antes → depois" */
(function () {
    var IGNORAR = /^(auditoria_antes|acao|csrf_token|form_login|permanecer_logado)$/i;
    var SENSIVEL = /senha|password|secret|token|codigo|arquivo|foto/i;

    function valorCampo(campo) {
        if (!campo || !campo.name) return null;
        if (campo.disabled || campo.type === "file" || campo.type === "password") return null;
        if (SENSIVEL.test(campo.name) || IGNORAR.test(campo.name)) return null;
        if (campo.type === "checkbox" || campo.type === "radio") {
            return campo.checked ? (campo.value || "on") : null;
        }
        if (campo.tagName === "SELECT" && campo.multiple) {
            return Array.prototype.map.call(campo.selectedOptions, function (o) {
                return o.value;
            }).filter(Boolean).join(", ");
        }
        return campo.value;
    }

    function snapshotForm(form) {
        if (!form || form.getAttribute("data-sem-auditoria") === "1") return;
        if ((form.method || "get").toLowerCase() === "get") return;
        if (form.querySelector('input[name="auditoria_antes"]')) return;
        if (form.querySelector('input[type="password"]')) return;
        var dados = {};
        Array.prototype.forEach.call(form.elements || [], function (campo) {
            if (!campo.name) return;
            if (/_antes$|^antes_/.test(campo.name)) return;
            var v = valorCampo(campo);
            if (v === null || v === undefined || String(v).trim() === "") return;
            if (Object.prototype.hasOwnProperty.call(dados, campo.name) && dados[campo.name]) {
                dados[campo.name] = dados[campo.name] + ", " + v;
            } else {
                dados[campo.name] = String(v);
            }
        });
        if (!Object.keys(dados).length) return;
        var hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.name = "auditoria_antes";
        hidden.value = JSON.stringify(dados);
        form.appendChild(hidden);
    }

    function preparar() {
        document.querySelectorAll("form").forEach(snapshotForm);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", preparar);
    } else {
        preparar();
    }
})();

/* Dados da empresa: matriz só para filial; confirmar antes de apagar campos já salvos */
(function () {
    document.addEventListener("change", function (ev) {
        var sel = ev.target;
        if (!sel || sel.name !== "tipo_unidade") return;
        var bloco = sel.closest("[data-unidade]");
        if (!bloco) return;
        bloco.querySelectorAll("[data-so-filial]").forEach(function (el) {
            el.hidden = sel.value !== "filial";
        });
    });

    document.addEventListener("submit", function (ev) {
        var form = ev.target;
        if (!form || !form.querySelector) return;
        var limpar = form.querySelector("input[name='limpar_vazios']");
        if (!limpar || !limpar.checked) return;
        var nomes = [];
        form.querySelectorAll("[data-empresa] input[type='text'], [data-empresa] input[type='email'], [data-empresa] input[type='date'], [data-empresa] select").forEach(function (campo) {
            var original = campo.tagName === "SELECT"
                ? (Array.prototype.find.call(campo.options, function (o) { return o.defaultSelected; }) || {}).value
                : campo.defaultValue;
            if (original && !String(campo.value || "").trim()) {
                var rotulo = campo.closest(".form-group") && campo.closest(".form-group").querySelector("label");
                nomes.push(rotulo ? rotulo.textContent.trim() : campo.name);
            }
        });
        if (!nomes.length) return;
        if (!window.confirm("Apagar estes dados já salvos?\n\n- " + nomes.join("\n- "))) ev.preventDefault();
    }, true);
})();
