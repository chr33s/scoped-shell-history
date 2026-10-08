package history

import (
	"fmt"
	"strings"

	"github.com/chr33s/shistory/internal/config"
	"github.com/chr33s/shistory/internal/db"
	"github.com/chr33s/shistory/internal/scope"
)

type Event struct {
	ID        int64  `json:"id"`
	Session   string `json:"session_id"`
	Seq       int64  `json:"seq"`
	StartedAt int64  `json:"started_at"`
	Duration  *int64 `json:"duration_ms"`
	Command   string `json:"command"`
	Status    *int   `json:"exit_status"`
	CWD       string `json:"cwd"`
	ScopeType string `json:"scope_type"`
	ScopePath string `json:"scope_path"`
	Shell     string `json:"shell"`
	Hostname  string `json:"hostname"`
	TTY       string `json:"tty"`
}

func Record(s *db.Store, c config.Config, e Event) error {
	if e.Session == "" || e.Seq < 1 || e.StartedAt < 0 || e.Shell == "" {
		return fmt.Errorf("record requires session, positive seq, shell, and nonnegative started-at")
	}
	if e.Status != nil && (*e.Status < 0 || *e.Status > 255) {
		return fmt.Errorf("status must be between 0 and 255")
	}
	if e.Duration != nil && *e.Duration < 0 {
		return fmt.Errorf("duration must be nonnegative")
	}
	if c.Ignore(e.Command, e.Status) {
		return nil
	}
	sc, err := scope.Detect(c, e.CWD)
	if err != nil {
		return err
	}
	_, err = s.Exec(`INSERT INTO history(session_id,seq,started_at,duration_ms,command,exit_status,cwd,scope_type,scope_path,shell,hostname,tty)
		VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(session_id,seq) DO NOTHING`,
		e.Session, e.Seq, e.StartedAt, e.Duration, e.Command, e.Status, sc.CWD, sc.Type, sc.Path, e.Shell, e.Hostname, e.TTY)
	return err
}

type Query struct {
	Scope    string
	CWD      string
	Text     string
	Prefix   *string
	Limit    int
	Dedupe   bool
	Failed   bool
	Session  string
	Hostname string
	BeforeID int64
	AfterID  int64
}

const columns = `id,session_id,seq,started_at,duration_ms,command,exit_status,cwd,scope_type,scope_path,shell,COALESCE(hostname,''),COALESCE(tty,'')`

func List(s *db.Store, q Query) ([]Event, error) {
	if q.Limit < 1 || q.Limit > 100000 {
		return nil, fmt.Errorf("limit must be between 1 and 100000")
	}
	where, args := []string{"1=1"}, []any{}
	add := func(clause string, values ...any) { where = append(where, clause); args = append(args, values...) }
	if q.Scope != "" {
		add("scope_path = ?", q.Scope)
	}
	if q.CWD != "" {
		add("cwd = ?", q.CWD)
	}
	if q.Text != "" {
		pattern := strings.NewReplacer("\\", "\\\\", "%", "\\%", "_", "\\_").Replace(q.Text)
		add(`command LIKE ? ESCAPE '\'`, "%"+pattern+"%")
	}
	if q.Prefix != nil {
		add("substr(command,1,length(?)) = ?", *q.Prefix, *q.Prefix)
	}
	if q.Failed {
		add("exit_status <> 0")
	}
	if q.Session != "" {
		add("session_id = ?", q.Session)
	}
	if q.Hostname != "" {
		add("hostname = ?", q.Hostname)
	}
	order := "DESC"
	if q.BeforeID != 0 || q.AfterID != 0 {
		id, op := q.BeforeID, "<"
		if q.AfterID != 0 {
			id, op, order = q.AfterID, ">", "ASC"
		}
		var started int64
		if err := s.QueryRow("SELECT started_at FROM history WHERE id = ?", id).Scan(&started); err != nil {
			return nil, fmt.Errorf("navigation cursor: %w", err)
		}
		add("(started_at,id) "+op+" (?,?)", started, id)
	}
	sql := "SELECT " + columns + " FROM history WHERE " + strings.Join(where, " AND ") + " ORDER BY started_at " + order + ", id " + order
	// With dedupe enabled, stream matches until the requested number of displayed rows.
	if !q.Dedupe {
		sql += " LIMIT ?"
		args = append(args, q.Limit)
	}
	rows, err := s.Query(sql, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	result := []Event{}
	var last string
	for rows.Next() {
		var e Event
		if err := rows.Scan(&e.ID, &e.Session, &e.Seq, &e.StartedAt, &e.Duration, &e.Command, &e.Status, &e.CWD, &e.ScopeType, &e.ScopePath, &e.Shell, &e.Hostname, &e.TTY); err != nil {
			return nil, err
		}
		if q.Dedupe && len(result) > 0 && last == e.Command {
			continue
		}
		result = append(result, e)
		last = e.Command
		if len(result) == q.Limit {
			break
		}
	}
	return result, rows.Err()
}
