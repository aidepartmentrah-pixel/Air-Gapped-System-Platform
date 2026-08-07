# Obsidian Guide

Obsidian is a local markdown note-taking app, useful for keeping operational notes and
this kit's documentation searchable on the server itself. Installed by
`07_install_scripts/install_obsidian.sh` from
`05_documentation_tools/obsidian/obsidian_1.12.7_amd64.deb` plus its dependency packages
in the `deps/` subfolder.

## Launching Obsidian

From the applications menu, or from a terminal:
```
obsidian
```

## First-time vault setup

1. On first launch, choose **Open folder as vault**.
2. Point it at a folder where you want to keep notes — for example, a copy of this kit's
   `08_documentation/` folder, so all the manuals become searchable and cross-linkable.
3. Obsidian creates a hidden `.obsidian/` config folder inside — this is normal.

## Notes

- Obsidian runs entirely locally; it does not require internet access to function.
- Do not enable Obsidian Sync or community plugin downloads on this server — both require
  internet access that this server does not have.
