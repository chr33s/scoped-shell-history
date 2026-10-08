package main

import (
	"fmt"
	"os"

	"github.com/chr33s/shistory/internal/cli"
)

func main() {
	if err := cli.Run(os.Args[1:], os.Stdout, os.Stderr); err != nil {
		fmt.Fprintln(os.Stderr, "shistory:", err)
		os.Exit(1)
	}
}
