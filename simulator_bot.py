
import time
import sys
import random

# Simulatore di API Sports
class APISimulator:
    def __init__(self):
        self.state = "1H"
        self.home_goals = 0
        self.away_goals = 0
        self.elapsed = 0
        
    def get_match_data(self):
        # Avanzamento logico
        if self.elapsed >= 90:
            self.state = "FT"
        elif self.elapsed >= 45 and self.state == "1H":
            self.state = "HT"
        elif self.state == "HT":
            self.state = "2H"
            self.elapsed = 46
        
        self.elapsed += 15 # Avanzamento veloce
        if random.random() > 0.7: self.home_goals += 1
        
        return {
            "response": [{
                "fixture": {"status": {"short": self.state, "elapsed": self.elapsed}},
                "goals": {"home": self.home_goals, "away": self.away_goals},
                "teams": {"home": {"name": "Juve"}, "away": {"name": "Milan"}}
            }]
        }

def genera_e_invia_stats_mock(match_id):
    print(f"\n📊 [SIMULAZIONE] Generazione statistiche per match {match_id}...")
    # Simuliamo il ritardo di generazione
    time.sleep(1)
    print("✅ [SIMULAZIONE] Statistiche generate (stats.png). Invio a Telegram...")

def main():
    api = APISimulator()
    match_id = 1511591
    print("🚀 Avvio Simulatore Partita Fast...")

    while True:
        data = api.get_match_data()
        match = data['response'][0]
        status = match['fixture']['status']['short']
        goals = match['goals']
        
        print(f"LIVE: {status} | {goals['home']}-{goals['away']}")
        
        if status == "HT":
            print("🏁 Fine primo tempo rilevato. Attesa 10 secondi per stats...")
            time.sleep(10)
            genera_e_invia_stats_mock(match_id)
            print("🔄 Ripresa monitoraggio 2° tempo...")
            
        elif status == "FT":
            print("🏁 Fischio finale rilevato. Attesa 10 secondi per stats...")
            time.sleep(10)
            genera_e_invia_stats_mock(match_id)
            print("🛑 Simulazione conclusa.")
            break
            
        time.sleep(2) # Pausa tra i cicli

if __name__ == "__main__":
    main()
