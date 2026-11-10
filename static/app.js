// Front-end mínimo que consome a API do AlertaBairro.
// Segurança: todo texto vindo da API entra via textContent (nunca innerHTML) -> sem XSS.
"use strict";

const $ = (id) => document.getElementById(id);
const CAMPOS = ["nome", "cidade", "uf", "latitude", "longitude", "area_de_risco"];

function mensagem(texto, tipo) {
  const el = $("mensagem");
  el.textContent = texto;
  el.className = tipo || "";
}

async function api(metodo, url, corpo) {
  const opcoes = { method: metodo, headers: {} };
  if (corpo !== undefined) {
    opcoes.headers["Content-Type"] = "application/json";
    opcoes.body = JSON.stringify(corpo);
  }
  const resp = await fetch(url, opcoes);
  const dados = resp.status === 204 ? null : await resp.json().catch(() => null);
  if (!resp.ok) {
    let texto = (dados && dados.erro) || `Erro ${resp.status}`;
    if (dados && dados.detalhes) {
      texto += ": " + Object.entries(dados.detalhes).map(([c, m]) => `${c} (${m})`).join("; ");
    }
    throw new Error(texto);
  }
  return dados;
}

function celula(texto) {
  const td = document.createElement("td");
  td.textContent = texto;
  return td;
}

function botao(texto, classe, acao) {
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = texto;
  if (classe) b.className = classe;
  b.addEventListener("click", acao);
  return b;
}

async function carregarBairros() {
  const corpo = $("lista-bairros");
  corpo.replaceChildren();
  try {
    const bairros = await api("GET", "/api/bairros");
    if (!bairros.length) {
      const tr = document.createElement("tr");
      const td = celula("Nenhum bairro cadastrado.");
      td.colSpan = 4; td.className = "vazio";
      tr.appendChild(td); corpo.appendChild(tr);
      return;
    }
    for (const b of bairros) {
      const tr = document.createElement("tr");
      tr.append(celula(b.nome), celula(`${b.cidade}/${b.uf}`), celula(b.area_de_risco));
      const acoes = document.createElement("td");
      acoes.className = "botoes";
      acoes.append(
        botao("Verificar clima", "", (e) => verificar(b.id, e.target)),
        botao("Editar", "secundario", () => editar(b)),
        botao("Excluir", "perigo", () => excluir(b))
      );
      tr.appendChild(acoes);
      corpo.appendChild(tr);
    }
  } catch (e) {
    mensagem(e.message, "erro");
  }
}

async function carregarAlertas() {
  const lista = $("lista-alertas");
  lista.replaceChildren();
  try {
    const alertas = await api("GET", "/api/alertas");
    if (!alertas.length) {
      const li = document.createElement("li");
      li.textContent = "Nenhum alerta emitido ainda. Clique em \"Verificar clima\".";
      li.className = "vazio";
      lista.appendChild(li);
      return;
    }
    for (const a of alertas) {
      const li = document.createElement("li");
      li.className = a.nivel;
      const titulo = document.createElement("strong");
      titulo.textContent = `${a.bairro} - ${a.cidade}/${a.uf}`;
      const texto = document.createElement("div");
      texto.textContent = a.mensagem;
      const quando = document.createElement("small");
      quando.textContent = `Emitido em ${new Date(a.criado_em).toLocaleString("pt-BR")}`;
      li.append(titulo, texto, quando);
      lista.appendChild(li);
    }
  } catch (e) {
    mensagem(e.message, "erro");
  }
}

function lerFormulario() {
  return {
    nome: $("nome").value.trim(),
    cidade: $("cidade").value.trim(),
    uf: $("uf").value.trim().toUpperCase(),
    latitude: Number($("latitude").value),
    longitude: Number($("longitude").value),
    area_de_risco: $("area_de_risco").value,
  };
}

function limparFormulario() {
  $("form-bairro").reset();
  $("bairro-id").value = "";
  $("titulo-form").textContent = "Cadastrar bairro monitorado";
  $("btn-salvar").textContent = "Cadastrar";
  $("btn-cancelar").hidden = true;
}

function editar(b) {
  $("bairro-id").value = b.id;
  for (const c of CAMPOS) $(c).value = b[c];
  $("titulo-form").textContent = `Editando: ${b.nome}`;
  $("btn-salvar").textContent = "Salvar alterações";
  $("btn-cancelar").hidden = false;
  $("nome").focus();
}

async function excluir(b) {
  if (!confirm(`Excluir "${b.nome}" e todos os alertas dele?`)) return;
  try {
    await api("DELETE", `/api/bairros/${b.id}`);
    mensagem("Bairro excluído.", "ok");
    await Promise.all([carregarBairros(), carregarAlertas()]);
  } catch (e) {
    mensagem(e.message, "erro");
  }
}

async function verificar(id, btn) {
  btn.disabled = true;
  try {
    const r = await api("POST", `/api/bairros/${id}/verificar`);
    const n = r.alertas.length;
    mensagem(n ? `${n} alerta(s) emitido(s) para ${r.bairro.nome}. Receptores notificados: ${r.receptores_notificados}.`
               : `Sem risco previsto para ${r.bairro.nome} nos próximos 3 dias.`, "ok");
    await carregarAlertas();
  } catch (e) {
    mensagem(e.message, "erro");
  } finally {
    btn.disabled = false;
  }
}

$("form-bairro").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const id = $("bairro-id").value;
  try {
    if (id) {
      await api("PUT", `/api/bairros/${id}`, lerFormulario());
      mensagem("Bairro atualizado.", "ok");
    } else {
      await api("POST", "/api/bairros", lerFormulario());
      mensagem("Bairro cadastrado.", "ok");
    }
    limparFormulario();
    await carregarBairros();
  } catch (e) {
    mensagem(e.message, "erro");
  }
});
$("btn-cancelar").addEventListener("click", () => { limparFormulario(); mensagem(""); });

carregarBairros();
carregarAlertas();
