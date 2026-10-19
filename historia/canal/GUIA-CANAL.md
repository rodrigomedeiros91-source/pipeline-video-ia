# The Myth Troll: guia de criação do canal

Arquivos nesta pasta:
- `avatar.png` (800×800): foto do canal.
- `banner.jpg` (2560×1440, 1,2 MB): imagem do banner.
- `marca-dagua.png` (150×150): marca d'água que aparece nos vídeos.
- `banner-previa-area-segura.png`: só para conferência. O retângulo vermelho é o que aparece em todos os aparelhos.

## 1. Criar o canal (conta de marca)

1. youtube.com → foto de perfil (canto superior direito) → **Configurações** → **Adicionar ou gerenciar canais** → **Criar um canal**.
2. Nome: **The Myth Troll** → aceitar → criar. Isso gera uma conta de marca separada do seu canal pessoal.
3. YouTube Studio do canal novo → **Personalização** → **Informações básicas** → **Identificador**: `@TheMythTroll` → **Publicar**.
4. **Verifique o telefone** em youtube.com/verify. Sem isso não dá para subir **thumbnail personalizada** nem vídeos com mais de 15 min.

## 2. Personalização (Studio → Personalização)

**Branding**
- Foto: `avatar.png`
- Imagem do banner: `banner.jpg` (aceite o recorte sugerido; o texto já está dentro da área segura)
- Marca d'água do vídeo: `marca-dagua.png`, exibir **o vídeo todo**

**Informações básicas → Descrição** (colar):

```
History is full of "facts" that never happened. I'm Snorri, a 1,000-year-old Norwegian troll who has watched humans get history wrong for centuries, and I'm here to set the record straight.

Here I take apart the myths, misquotes and "everyone knows" stories that are completely wrong: fake famous quotes, misunderstood historical figures, medieval myths, Roman legends and Wild West tall tales. Real sources, real evidence, zero patience for nonsense.

🗓 New deep dives and Shorts regularly
📚 Every claim is sourced, with links in each video description
😏 Skeptical, funny, and only slightly grumpy

Subscribe if you'd rather know what actually happened.
```

- Links: deixe vazio por enquanto (dá para pôr TikTok depois).
- E-mail de contato: opcional (um e-mail do canal, não o pessoal).

**Layout**: preencha depois do primeiro vídeo.
- Trailer para quem não é inscrito: o primeiro Short ou o vídeo longo.
- Seções em destaque: *Shorts*, *Vídeos*, *Playlists*.

## 3. Configurações (Studio → Configurações)

**Canal → Informações básicas**
- País de residência: **Brasil** (precisa ser o real, por causa da monetização e dos impostos).
- Palavras-chave (colar):

```
history, history myths, myths debunked, historical myths, history facts, common misconceptions, fake quotes, famous misquotes, history explained, myth busting, medieval history, roman history, funny history, true history, the myth troll, snorri
```

**Canal → Configurações avançadas**
- Público: **"Não, definir este canal como não destinado a crianças"**. Isso é importante: o troll é desenho, mas o conteúdo é para adultos. Marcar como infantil desliga comentários e reduz muito a receita.

**Padrões de envio → Informações básicas**
- Descrição padrão: deixe em branco (a Fábrica gera a `descricao.txt` de cada vídeo).
- Tags: `history, history myths, myths debunked, the myth troll`
- Visibilidade: **Privado** (você agenda no upload).

**Padrões de envio → Configurações avançadas**
- Idioma do vídeo: **Inglês**. Idioma da legenda: **Inglês**.
- Categoria: **Educação**.
- Comentários: **Permitir todos**, ou "reter os potencialmente impróprios".
- Conteúdo alterado ou sintético: **Não**. O vídeo é desenho, sem pessoas reais simuladas, e a voz é de um narrador fictício. Marque **Sim** só se algum dia o vídeo mostrar uma pessoa real ou um evento real de forma realista gerada por IA.

## 4. Playlists (crie quando o primeiro vídeo do tema subir)

| Playlist | Descrição curta |
|---|---|
| Fake Famous Quotes | Famous quotes their "authors" never said, and who really did. |
| History Myths Debunked | The biggest "everyone knows" history facts that are wrong. |
| Medieval Myths | Flat earth, chastity belts, dirty peasants: what the Middle Ages were really like. |
| Roman Myths | Gladiators, vomitoriums and Nero's fiddle, fact-checked. |
| Wild West Myths | Gunfights, cowboys and outlaws vs. the real frontier. |
| Misunderstood Historical Figures | Famous people history got wrong. |

## 5. A cada vídeo (resumo; a parte 4 vai automatizar boa parte)

1. Subir `historia/videos/<slug>/video.mp4`.
2. Título e descrição: copiar de `descricao.txt` (o título está na linha `TITLE:`). As tags estão na linha `TAGS:`.
3. Legendas: **Legendas → Adicionar idioma (Inglês) → Enviar arquivo → `legendas.srt`**.
4. Thumbnail personalizada (exige telefone verificado).
5. Playlist do tema.
6. Agendar.
