import os
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional

import dulwich.errors
from dulwich import porcelain as git

from . import addresslib

STACK_PATTERN = re.compile(
    rb"(\t\[ *\d+] 0x[0-9A-F]+ .*\+[0-9A-F]+) -> (?P<id>\d+)\+0x[0-9A-F]+"
)


class CrashLogProcessor:
    def __init__(self, game: str, delete_callback: Callable[[Path], None]):
        self.database = addresslib.get_database(game)
        self.git_repo = os.path.join(os.path.dirname(__file__), game)
        self.delete_callback = delete_callback

    def clone_database(self) -> None:
        if not os.path.exists(self.git_repo):
            try:
                git.clone(
                    self.database.remote,
                    self.git_repo,
                    branch=self.database.branch,
                )
            except git.Error as e:
                print(f"Error cloning repository: {e}")
                raise

    def update_database(self) -> None:
        try:
            with git.Repo(self.git_repo) as repo:
                git.pull(repo, self.database.remote)
                if git.active_branch(repo) != self.database.branch:
                    git.checkout_branch(repo, self.database.branch)
        except dulwich.errors.NotGitRepository:
            self.clone_database()
        except dulwich.errors.GitProtocolError as e:
            print(f"Error during git operation: {e}")
            raise

    def get_database_path(self) -> str:
        return os.path.join(self.git_repo, self.database.database_file)

    def process_log(self, log: Path) -> None:
        crash_log = CrashLog(log)

        addr_ids = set()
        width = 0
        for line in crash_log.call_stack:
            match = STACK_PATTERN.match(line)
            if not match:
                continue
            addr_ids.add(int(match.group("id")))
            width = max(width, len(match.group(0)) + 1)

        if not addr_ids:
            return
        id_list = sorted(addr_ids)

        id_lookup = self.lookup_ids(id_list)
        if not id_lookup:
            return

        crash_log.rewrite_call_stack(lambda a_line: self.add_name(a_line, id_lookup, width))
        if crash_log.changed:
            self.delete_callback(log)
            crash_log.write_file(log)

    @staticmethod
    def add_name(line: bytes, id_lookup: Dict[int, bytes], width: int) -> bytes:
        match = STACK_PATTERN.match(line)
        if not match:
            return line

        stack_frame = match.group(0)
        name = id_lookup.get(int(match.group("id")))
        if not name:
            return stack_frame + b"\n"

        name = name.rstrip(b"_*")
        return stack_frame.ljust(width, b' ') + name + b"\n"

    def lookup_ids(self, id_list: List[int]) -> Dict[int, bytes]:
        database = self.get_database_path()
        if not os.path.exists(database):
            return {}

        lookup = {}
        with IdScanner(database) as scanner:
            for addr_id in id_list:
                name = scanner.find(addr_id)
                if name:
                    lookup[addr_id] = name
        return lookup


class CrashLog:
    def __init__(self, path: Path):
        self.pre_call_stack: List[bytes] = []
        self.call_stack: List[bytes] = []
        self.post_call_stack: List[bytes] = []
        self.changed = False

        self.read_file(path)

    def visit_call_stack(self, callback: Callable[[bytes], None]) -> None:
        for line in self.call_stack:
            callback(line)

    def rewrite_call_stack(self, callback: Callable[[bytes], bytes]) -> None:
        new_call_stack = [callback(line) for line in self.call_stack]
        if new_call_stack != self.call_stack:
            self.changed = True
            self.call_stack = new_call_stack

    def write_file(self, path: Path) -> None:
        with path.open("wb") as f:
            f.writelines(self.pre_call_stack)
            f.writelines(self.call_stack)
            f.writelines(self.post_call_stack)

    def read_file(self, path: Path) -> None:
        with path.open("rb") as f:
            while True:
                line = f.readline()
                if not line:
                    return

                self.pre_call_stack.append(line)
                if line == b"PROBABLE CALL STACK:\n":
                    break

            while True:
                line = f.readline()
                if not line:
                    return

                if line == b"\n":
                    break
                elif line == b"REGISTERS:\n":
                    self.post_call_stack.append(b"\n")
                    break

                self.call_stack.append(line)

            while True:
                self.post_call_stack.append(line)

                line = f.readline()
                if not line:
                    return


class IdScanner:
    def __init__(self, database: str):
        self.database = database
        self.f = None
        self.nextLine = b""

    def __enter__(self):
        if os.path.exists(self.database):
            self.f = open(self.database, "rb")
            self.f.readline()
            self.nextLine = self.f.readline()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if self.f:
            self.f.close()

    def find(self, addr_id: int) -> Optional[bytes]:
        while self.nextLine:
            line_id, name = tuple(self.nextLine.split())
            parsed_id = int(line_id)

            if parsed_id == addr_id:
                return name
            elif parsed_id > addr_id:
                return None

            self.nextLine = self.f.readline()
        return None