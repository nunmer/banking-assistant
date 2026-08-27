// Mock MIB API — returns HTTP 200 with a fake transaction ID for any
// operation. Real MIB's contract is not known yet (see forte-mib3-webview
// for the separate, already-real auth handshake — this service has nothing
// to do with that). Swap for the real MIB by pointing MIB_API_BASE at the
// real endpoint; the orchestrator's mib.py client does not change.
package main

import (
	"crypto/rand"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strings"
	"time"
)

type account struct {
	AccountID string            `json:"account_id"`
	Currency  string            `json:"currency"`
	Balance   int               `json:"balance"`
	Name      map[string]string `json:"name"`
}

// Every pilot user gets the same plausible account set. Names are per-language
// base forms the orchestrator drops into confirm templates.
var accounts = []account{
	{AccountID: "ACC-KZT-001", Currency: "KZT", Balance: 245000, Name: map[string]string{"ru-RU": "Тенговый", "kk-KZ": "Теңгелік", "en-US": "Tenge"}},
	{AccountID: "ACC-USD-001", Currency: "USD", Balance: 1200, Name: map[string]string{"ru-RU": "Долларовый", "kk-KZ": "Долларлық", "en-US": "Dollar"}},
	{AccountID: "ACC-EUR-001", Currency: "EUR", Balance: 640, Name: map[string]string{"ru-RU": "Евро", "kk-KZ": "Еуро", "en-US": "Euro"}},
}

type mibResponse struct {
	Status    string `json:"status"`
	TxID      string `json:"tx_id"`
	Timestamp string `json:"timestamp"`
	Message   string `json:"message"`
}

func newTxID() string {
	b := make([]byte, 4)
	_, _ = rand.Read(b)
	return fmt.Sprintf("MOCK-%X", b)
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func main() {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})

	// The user's accounts — used to resolve "тенговый/долларовый" to real IDs.
	mux.HandleFunc("GET /accounts/{user_id}", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]any{
			"user_id":  r.PathValue("user_id"),
			"accounts": accounts,
		})
	})

	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case http.MethodGet, http.MethodPost, http.MethodPut:
		default:
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		path := strings.TrimPrefix(r.URL.Path, "/")
		txID := newTxID()
		writeJSON(w, http.StatusOK, mibResponse{
			Status:    "success",
			TxID:      txID,
			Timestamp: time.Now().UTC().Format(time.RFC3339),
			Message:   fmt.Sprintf("Operation /%s completed. Ref: %s", path, txID),
		})
	})

	log.Println("mib-service listening on :8001")
	if err := http.ListenAndServe(":8001", mux); err != nil {
		log.Fatal(err)
	}
}
