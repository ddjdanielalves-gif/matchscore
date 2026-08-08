# MatchScore

Plataforma web de **análise probabilística de partidas do futebol brasileiro**
(Campeonato Brasileiro Série A). Calcula a probabilidade de vitória do
mandante, empate e vitória do visitante a partir de dados como **forma
recente, força ELO, lesões, suspensões, cartões e posição na tabela**.

> ⚠️ **Aviso importante:** as probabilidades são **estimativas estatísticas**.
> Futebol é imprevisível: o resultado de uma partida pode ser
> **completamente aleatório** e divergir de qualquer estimativa. Esta
> ferramenta **não constitui recomendação de aposta**.

## Stack

- **Backend**: FastAPI + httpx (pasta `backend/`)
- **Frontend**: React + Vite + TypeScript (pasta `frontend/`)

## Fonte de dados (gratuita)

- **api-football direto** (dashboard.api-football.com) — plano grátis, sem
  cartão de crédito, **100 requisições/dia**. O plano grátis bloqueia consultas
  por `league + season` atuais (só libera temporadas 2022–2024), então o app
  usa uma estratégia que respeita essas limitações:
  - **Jogos próximos**: janela de 3 dias via `/fixtures?date=...` (dados reais).
  - **Previsões reais**: `/predictions?fixture=...` retorna os percentuais
    atuais da api-football (real), combinados com o nosso modelo.
  - **Força e tabela**: usa a última temporada completa acessível
    (`MATCH_BASE_SEASON`, 2024) para ELO, forma, ataque/defesa e classificação.
  - **Histórico H2H**: os últimos confrontos diretos vêm reais da API.
  - **Lesões/suspensões/cartões**: não disponíveis no plano grátis — o app
    avisa na interface e não inventa jogadores (fatores zerados, médias da
    liga para cartões).
  - Chamadas espaçadas + cache em memória para não estourar a cota/dia.
- **Modo demo** (sem chave) — dados simulados realistas e determinísticos,
  marcados como *demo* na interface.

O provider também aceita o host legado do RapidAPI
(`api-football-v1.p.rapidapi.com`): o app detecta o host e troca o cabeçalho
de autenticação automaticamente.

Se algum endpoint falhar ou a cota acabar, o app degrada com **elegância**:
usa estimativas honestas (média da liga) e avisa na interface em vez de
inventar dados.

## Rodar localmente

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows PowerShell
pip install -r requirements.txt
uvicorn app.main:app --port 8001
```

Sem `MATCH_API_KEY`, o app roda em **modo demo**. Para usar dados reais,
registre grátis em https://dashboard.api-football.com (sem cartão) e copie a
chave da dashboard:

```bash
$env:MATCH_API_KEY = "SUA_CHAVE"
```

### Frontend (desenvolvimento)

```bash
cd frontend
npm install
npm run dev
```

Abra http://localhost:5174. O Vite faz proxy de `/api` para o backend em
`127.0.0.1:8001` (use `VITE_API_PORT` para mudar a porta).

### Produção (Render, serviço único)

O `frontend/dist` é versionado: o backend serve o build estático e a API na
mesma origem.

1. Crie um repositório público no GitHub e suba a pasta `matchscore/`.
2. No Render: **New → Web Service**, Build: `pip install -r backend/requirements.txt`,
   Start: `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
3. Variável de ambiente: `MATCH_API_KEY` (opcional — sem ela roda em demo).

Alternativamente, use o `render.yaml` incluído.

## Configuração (env vars, prefixo `MATCH_`)

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `MATCH_API_KEY` | vazio | Chave da api-football (direta ou RapidAPI). Vazia = modo demo |
| `MATCH_API_HOST` | `v3.football.api-sports.io` | Host da API (troque p/ `api-football-v1.p.rapidapi.com` no legado) |
| `MATCH_API_BASE_URL` | `https://v3.football.api-sports.io` | Base URL da API |
| `MATCH_LEAGUE_ID` | `71` | Brasileirão Série A |
| `MATCH_SEASON` | `2026` | Temporada atual |
| `MATCH_BASE_SEASON` | `2024` | Última temporada completa acessível no plano grátis (força e tabela) |
| `MATCH_MOCK` | `false` | Força modo demo mesmo com chave |
| `MATCH_CACHE_TTL_SECONDS` | `1800` | Cache em memória (economiza quota gratuita) |

## Modelo de probabilidade

- **ELO** atualizado com resultados reais da temporada base (fator K = 32,
  vantagem de mando +100).
- **Gols esperados (xG)** via modelo Poisson a partir de forças de ataque e
  defesa de cada time.
- **Ajustes**: forma recente, lesões, suspensões, cartões, mando de campo e
  posição na tabela.
- **Blend com a API**: quando `/predictions` retorna percentuais reais da
  api-football, o resultado final combina o modelo (45%) com a leitura da API
  (55%) — a API é mais atual, por isso pesa mais. A análise mostra os dois
  lado a lado.
- Cada fator gera um **deslocamento em pontos percentuais** exibido na análise,
  para o usuário entender o que moveu a estimativa.

## API

| Rota | Descrição |
| --- | --- |
| `GET /api/info` | Metadados e texto do aviso |
| `GET /api/matches?round=N` | Jogos futuros da rodada |
| `GET /api/matches/{id}` | Detalhe de uma partida |
| `GET /api/matches/{id}/analysis` | Probabilidades e fatores |
| `GET /api/standings` | Classificação |

## Aviso legal

Ferramenta educacional/experimental. Não é recomendação de aposta nem previsão
de resultado.

## Versão Android (APK)

O app web vira um APK Android via **Capacitor**. O build acontece na nuvem com
**GitHub Actions** (não precisa de Android Studio na sua máquina), e o download
fica em um **site (GitHub Pages)**. O app no celular tem a mesma cara da
página, incluindo o logo (foto na bola verde) no cabeçalho.

Fluxo:

1. **Subir o repositório** — criar um repo GitHub para o `matchscore` e dar
   push (os workflows em `.github/workflows/` fazem o resto).
2. **Deploy do backend no Render** — a partir do repo, criar um Web Service
   usando o `render.yaml` (serviço chamado `matchscore` → URL
   `https://matchscore.onrender.com`). No painel do Render, defina a variável
   `MATCH_API_KEY` (chave real da api-football).
3. **Apontar o APK para o backend** — criar uma *variable* no GitHub
   (Settings → Secrets and variables → Actions) chamada `API_URL` com o valor
   `https://matchscore.onrender.com`. O workflow a embute no app.
4. **Rodar o build** — na aba *Actions*, rodar o workflow **Build Android
   APK**. O APK assinado aparece na *Release* `apk` e como artefato do job.
5. **Site de download** — habilitar GitHub Pages (Source: GitHub Actions) e
   rodar **Deploy download page**. A página em `site/index.html` tem o botão de
   download e instruções de instalação.

Links úteis (após configurar):

- Download direto: `https://github.com/<seu-user>/matchscore/releases/latest/download/app-release.apk`
- Página de download: `https://<seu-user>.github.io/matchscore/`

Assinatura: a cada build o workflow gera um keystore novo. Para manter a mesma
chave entre builds (ex.: futura publicação na Play Store), defina o secret
`ANDROID_KEYSTORE_B64` (keystore em base64) e, opcionalmente,
`ANDROID_KEYSTORE_PASS` (senha; padrão `matchscore123`).

**Importante para o APK**: a base da API é definida no build pela variável
`VITE_API_URL` (o celular não enxerga `localhost`). Localmente, sem a variável,
o app usa a mesma origem (web).
