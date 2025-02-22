import apt
from humanize import naturalsize
from rich.columns import Columns
from rich.panel import Panel
from rich.text import Text
from rich.console import Group


class Package:
    def __init__(self, pkg: apt.Package):
        self.pkg = pkg
        if pkg.is_upgradable:
            self.icon = "↑"
        elif pkg.is_installed:
            self.icon = "✓"
        else:
            self.icon = " "
        self.version = pkg.candidate or pkg.installed or list(pkg.versions)[0]
        self.name = pkg.name
        self.simple = pkg.name == pkg.shortname
        self.summary = self.version.summary

    def __str__(self):
        return f"{self.icon} {self.name:20}\t{self.summary}"

    def to_text(self):
        return Text(" ").join(
            self.__row__(),
        )

    def __row__(self):
        return [
            Text(self.icon),
            Text(self.name, style="bold"),
            Text(self.summary or "", style="cyan"),
        ]

    def __columns__(self):
        return ["", "Name", "Description"]

    def __rich__(self):
        return self.to_text()

    def describe(self):
        def field(label, value):
            return f"{label + ':':20}[bold]{value}[/bold]"

        fields = [
            field("Version", self.version.version),
            field("Download Size", naturalsize(self.version.size)),
            field("Installed Size", naturalsize(self.version.installed_size)),
            field("Maintainer", self.version.record.get("Maintainer", "?")),
            field("Section", self.version.section),
            field("Priority", self.version.priority),
            field("Architecture", self.version.architecture),
        ]
        related = []
        for relation in (
            "Breaks",
            "Replaces",
            "Provides",
            "Conflicts",
            "Depends",
            "PreDepends",
            "Recommends",
            "Suggests",
        ):
            deps = self.version.get_dependencies(relation, "")
            texts = []
            for dep in deps:
                text = Text(dep.rawstr)
                text.highlight_regex(r"[<>=]\s+\S+", "dim")
                text.highlight_regex(r"[a-z]\S+", "bold cyan")
                texts.append(text)
            if texts:
                related.append(
                    Text(relation, style="bold") + Text(": ") + Text(", ").join(texts)
                )
        metadata = Columns(fields)
        relations = Columns(related)
        return Panel(
            Group(metadata, Text(), self.version.description, Text(), relations),
            title=self.to_text(),
        )
