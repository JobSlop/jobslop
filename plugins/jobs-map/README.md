# Jobs map — a jobslop plugin

Your search results on a map: a Jobs map tab with your search radius and a list, and a layer on the Search area map.

## What it adds

- **A Jobs map tab:** your current results (after your filters) on a map, with your search radius around the place in “Where?”. Jobs in the same town share one pin with a count; click a job in the list to fly to it.
- **A map layer:** “💼 Jobs from your search” on the Search area map.
- Remote jobs, and jobs whose place can't be found, are counted rather than pinned.

It comes with jobslop and is switched on by default (Settings → Plugins). It has no Python code, only screen code (`ui.js`).

## Making changes

See the plugin guide, `docs/PLUGINS.md` in the [jobslop repository](https://github.com/JobSlop/jobslop).
Raise `version` in `plugin.json` and publish a GitHub release tagged `v<version>`.

Licence: GPL-3.0.
