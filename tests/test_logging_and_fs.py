import io
import logging

from neoreef.common import fs
from neoreef.common import logging as nlog


def test_make_cli_logger_writes_console_and_file(tmp_path, capsys):
    log = nlog.make_cli_logger(tmp_path / "sub" / "run.log", name="neoreef.test")
    log.info("hello")
    log.debug("quiet")
    out = capsys.readouterr().out
    assert "hello" in out and "quiet" not in out          # console is INFO+
    text = (tmp_path / "sub" / "run.log").read_text(encoding="utf-8")
    assert "hello" in text and "quiet" in text            # file is DEBUG+
    assert nlog.make_cli_logger(tmp_path / "x.log", name="neoreef.test") is log  # idempotent
    assert len(log.handlers) == 2
    for h in list(log.handlers):
        h.close()
        log.removeHandler(h)


def test_make_metashape_logger_fans_out_and_never_raises(capsys):
    seen = []
    handle = io.StringIO()
    log = nlog.make_metashape_logger(handle, console_print=seen.append)
    log("one")
    log(2)
    assert seen == ["one", "2"]
    assert handle.getvalue() == "one\n2\n"
    assert "one" in capsys.readouterr().out

    def boom(_):
        raise RuntimeError("console closed")

    closed = io.StringIO()
    closed.close()
    log2 = nlog.make_metashape_logger(closed, console_print=boom)
    log2("still fine")   # must not raise


def test_make_metashape_logger_without_sinks(capsys):
    log = nlog.make_metashape_logger()
    log("stdout only")
    assert "stdout only" in capsys.readouterr().out


def test_fs_helpers(tmp_path):
    d = fs.ensure_dir(tmp_path / "a" / "b")
    assert d.is_dir()
    f = d / "f.txt"
    f.write_text("x")
    assert fs.safe_unlink(f) is True
    assert fs.safe_unlink(f) is False
    assert fs.safe_unlink(tmp_path / "a") is False       # directory: untouched
    (tmp_path / "src" / "sub").mkdir(parents=True)
    (tmp_path / "src" / "sub" / "x.js").write_text("1")
    fs.copy_tree(tmp_path / "src", tmp_path / "dst")
    (tmp_path / "src" / "sub" / "x.js").write_text("2")
    fs.copy_tree(tmp_path / "src", tmp_path / "dst")     # overwrite ok
    assert (tmp_path / "dst" / "sub" / "x.js").read_text() == "2"
