package scope

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/chr33s/scoped-shell-history/internal/config"
)

type Scope struct {
	CWD  string `json:"cwd"`
	Type string `json:"scope_type"`
	Path string `json:"scope_path"`
}

func Canonical(path string) (string, error) {
	path, err := config.Expand(path)
	if err != nil {
		return "", err
	}
	path, err = filepath.EvalSymlinks(path)
	if err != nil {
		return "", err
	}
	info, err := os.Stat(path)
	if err != nil {
		return "", err
	}
	if !info.IsDir() {
		return "", fmt.Errorf("not a directory: %s", path)
	}
	return path, nil
}

func Detect(c config.Config, cwd string) (Scope, error) {
	if cwd == "" {
		var err error
		cwd, err = os.Getwd()
		if err != nil {
			return Scope{}, err
		}
	}
	cwd, err := Canonical(cwd)
	if err != nil {
		return Scope{}, err
	}
	s := Scope{CWD: cwd, Type: "directory", Path: cwd}
	if c.Root.Git {
		ctx, cancel := context.WithTimeout(context.Background(), time.Second)
		defer cancel()
		cmd := exec.CommandContext(ctx, "git", "-C", cwd, "rev-parse", "--show-toplevel")
		// An ambient Git environment must not redirect detection into another repo.
		for _, entry := range os.Environ() {
			if !strings.HasPrefix(entry, "GIT_") {
				cmd.Env = append(cmd.Env, entry)
			}
		}
		if out, err := cmd.Output(); err == nil {
			root, err := Canonical(strings.TrimSuffix(string(out), "\n"))
			if err == nil {
				s.Type, s.Path = "project", root
				return s, nil
			}
		}
	}
	for dir := cwd; ; dir = filepath.Dir(dir) {
		for _, marker := range c.Root.Markers {
			if _, err := os.Stat(filepath.Join(dir, marker)); err == nil {
				s.Type, s.Path = "project", dir
				return s, nil
			}
		}
		if filepath.Dir(dir) == dir {
			break
		}
	}
	return s, nil
}
