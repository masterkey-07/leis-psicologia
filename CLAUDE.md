# Purpose of this folder

This folder is a curated legal reference for running a **psychology clinic (clínica de
psicologia) in São José dos Campos, São Paulo, Brazil**. It collects every norm that governs,
involves or touches on that activity, plus official websites and agencies to consult.

It is a subset of the parent repository (`../`, https://github.com/ctresb/leis), a corpus of Brazilian legislation converted to
Markdown. Nothing here is original legal text written by hand: the norms are **byte-for-byte
copies** of files from the parent corpus.

## Contents

- `normas/` — 712 copied norms, mirroring their original path in the parent repo
  (e.g. `normas/federal/leis-ordinarias/1962/lei-4119-1962-08-27.md` is
  `../federal/leis-ordinarias/1962/lei-4119-1962-08-27.md`). Each file starts with YAML
  frontmatter (`titulo`, `orgao`, `tipo`, `numero`, `data`, `ementa`, `revogada`, `fonte`).
- `INDICE.md` — index of all norms grouped by topic (profession, ethics/CFP, mental health/SUS,
  telehealth, data and medical records, vulnerable groups, consumer/civil/criminal, health
  plans, sanitary/tax/labor, São Paulo state, case law, treaties), with links to each file and
  its official source. Ends with a list of relevant norms **not** present in the corpus.
- `REFERENCIAS.md` — verified links to agencies and resources: CFP and CRP-06/SP, Ministério da
  Saúde, ANVISA, ANS, CNES, CVS-SP, São José dos Campos city hall (sanitary license, ISS, NFS-e,
  Diário do Município, Câmara), ANPD, Procon-SP, Simples Nacional, legislation search portals
  and crisis/referral services.
- `_selecao.json` — machine-readable list of every copied file and its category.

## Scope decisions

- Spheres: federal law, federal regulators, **CFP and CRP-06 (São Paulo) only** — other
  regional councils have no jurisdiction here —, São Paulo state law, case law and treaties.
- Relevance: norms directly about psychology/mental health, plus a hand-curated list of general
  norms that apply to a clinic (LGPD, CDC, ECA, LBI, telehealth, health plans, sanitary,
  tax and labor law).
- Deliberately excluded: university course authorizations, public job positions, funding
  transfers and CAPS accreditations for other municipalities, internal court acts, state
  hospital administration, honorary dates and street names.
- **São José dos Campos municipal law is not in the corpus**; it is covered only by links in
  `REFERENCIAS.md`.

## Guidance for AI assistants

- Answer questions about clinic compliance from these files first; cite the file path and the
  official `fonte` URL from its frontmatter.
- Texts are informative automatic conversions, **not** the official publication. Check
  `revogada` and remind the user to confirm the current version at the official source,
  especially CFP resolutions, the ANS Rol and city procedures, which change often.
- Do not edit files under `normas/`; they must stay identical to the parent corpus. To change
  the selection, regenerate it from `../` and update `INDICE.md` and `_selecao.json` together.
- Content language is Brazilian Portuguese; answer the user in the language they write in.
