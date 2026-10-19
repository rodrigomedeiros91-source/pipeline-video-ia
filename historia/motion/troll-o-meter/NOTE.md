# Troll-o-meter (Motion Maxing)

Vinheta que fecha cada capítulo e cada Short: o veredito do Snorri sobre o mito, num medidor desenhado a nanquim.

- **Ideia:** só este canal tem o "Troll-o-meter" (já era o fecho falado desde o wrong-inventors); o medidor dá corpo à piada.
- **Mundo:** o pergaminho dos cartões (`historia/estilo/pergaminho.png`), Patrick Hand como nas lousas, tinta #2B2118 e um só
  destaque, vermelho #B3261E = "veredito" (ponteiro, zona 5, nota). Os ~600 px da direita ficam livres para a pose do troll.
- **Batidas (30 fps, 2,7 s):** f0–14 o mostrador já está sendo traçado e o título cai de 1,35x (snapSettle); f12–40 o ponteiro
  sobe e hesita no 3 ("vai ser justo?"); f48 bate no veredito (crashIn, a única mola do filme); f49 a nota entra de 2,6x; no 5/5 o
  mostrador treme; f58–81 deriva lenta de escala (sem quadro morto). Na montagem o clipe roda uma vez e congela com zoom lento.
- **Real x inventado:** nada de imagem gerada; tudo é SVG/HTML. Os números são a nota do roteiro.
- **Portões (look.py / lint.mjs, 2026-10-17):** G0 PASS (2,70 s), G2 PASS, G3 PASS (fim parado 0,87 s no 4/5 e 0,80 s no 5/5),
  G5 PASS. G1/G4 no olho em look-4/sheet.jpg: um foco por quadro (o mostrador), texto ≥ 44 px (0,04 H), nota em 250 px.
  Movimento médio 0,5/255, abaixo da faixa humana: é uma vinheta calma de propósito; a hesitação no 3 é a pausa da piada.
- **Quadros descritos:** mostrador sendo traçado com o ponteiro deitado em "mostly true"; números entrando; ponteiro em pé no 3;
  ponteiro oscilando; ponteiro cravado no 4 (ou 5) com a nota vermelha embaixo; mesma imagem com leve aproximação.
- **Melhorar depois:** som de "tchac" no impacto (a montagem só tem narração e música); variante vertical própria para os Shorts.

Render: `CHROME_PATH=".../chrome.exe" node <skill>/scripts/render.mjs "file:///.../index.html?n=5" troll-o-meter-5.mp4`
(o runtime e o GSAP ficam em `runtime/`, fora do git: copie de `<skill>/runtime/motion.js` e `runtime/vendor/gsap.min.js`).
