# Linux Commands Reference

A cheat sheet of the commands you'll actually use while operating this server, for an IT
employee with limited Linux experience.

## Moving around

| Command | What it does |
|---|---|
| `pwd` | Print the current folder path |
| `ls -la` | List all files in the current folder, including hidden ones, with details |
| `cd <folder>` | Move into a folder |
| `cd ..` | Move up one folder |
| `cd ~` | Jump to your home folder |

## Looking at files

| Command | What it does |
|---|---|
| `cat <file>` | Print an entire file to the screen |
| `less <file>` | View a file page by page (press `q` to quit) |
| `nano <file>` | Edit a file with a simple, beginner-friendly editor (`Ctrl+O` save, `Ctrl+X` exit) |
| `tail -f <file>` | Watch a log file live as new lines are added (`Ctrl+C` to stop) |

## Docker basics

| Command | What it does |
|---|---|
| `docker ps` | List running containers |
| `docker ps -a` | List all containers, including stopped ones |
| `docker images` | List loaded images |
| `docker logs <name>` | Show a container's log output |
| `docker logs -f <name>` | Follow a container's log output live |
| `docker restart <name>` | Restart a container |
| `docker stop <name>` | Stop a container |
| `docker start <name>` | Start a stopped container |
| `docker exec -it <name> bash` | Open a shell inside a running container |
| `docker compose up -d` | Start every service defined in a `docker-compose.yml` in the background |
| `docker compose down` | Stop and remove every service defined in a `docker-compose.yml` |
| `docker compose logs -f` | Follow logs for every service in a compose stack |

## System health

| Command | What it does |
|---|---|
| `df -h` | Show disk space usage for all mounted drives |
| `free -h` | Show RAM and swap usage |
| `htop` | Live, interactive view of running processes and CPU/RAM usage (`q` to quit) |
| `systemctl status docker` | Check whether the Docker service is running |
| `hostname -I` | Show this server's IP address(es) |

## Copying files (from USB or between folders)

| Command | What it does |
|---|---|
| `cp <source> <destination>` | Copy a file |
| `cp -r <source-folder> <destination>` | Copy an entire folder |
| `rsync -avh <source> <destination>` | Copy files while preserving permissions, showing progress |
| `zip -r archive.zip <folder>` | Compress a folder into a zip file |
| `unzip archive.zip` | Extract a zip file |

## Long-running sessions (tmux)

If your terminal connection might drop (e.g. connecting over SSH), use `tmux` so
commands keep running even if you disconnect:

| Command | What it does |
|---|---|
| `tmux new -s work` | Start a new named session called "work" |
| `Ctrl+B` then `D` | Detach from the session (it keeps running in the background) |
| `tmux attach -t work` | Reattach to the "work" session later |
| `tmux ls` | List all active sessions |

## Folder trees

| Command | What it does |
|---|---|
| `tree` | Show a visual folder/file tree of the current directory |
| `tree -L 2` | Same, but only 2 levels deep |
