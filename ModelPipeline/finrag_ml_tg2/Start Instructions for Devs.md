

- Workspace 1, 2, 3.. N = is meant for sibling model / non-colliding architecture pipes if someone wants to develop them.
- The idea is that, subteams can develop parallel architectures by **extending**, reusing code from finrag_ml_tg1 workspace.
- Another critical idea is that experiments from a different architecture plan will not be merged back to finrag_ml_tg1, as we aim for preservance of 1 base prototype or orchestration architecture.
- Developing independent designs on different branches using *same* workspace is discouraged, as it will lead to code collisions or functional-descisions conflicts. Developing independent architectures on different workspaces is highly recommended.

For import guidance:
- Please resolve 3/4 levels of root and set highest parent root, access workspace 1 properly and use absolute imports.
- Do not edit workspace1 code. 