#!/usr/bin/env python3
"""给 7 个 locale 补 cultivation 域的 key（第十八批 D 段 D2）。

用法：python3 add_cultivation_locales.py [--check]

★ 格式纪律：locales/*.json 是 `json.dumps(..., ensure_ascii=False, indent=2,
  sort_keys=True) + "\n"` ⇒ 本脚本按同一口径写回，**不重排、不改别的 key**。
★ 口径纪律：7 个 locale **key 集合必须完全一致**（386 × 7 全齐的前例），
  所以每个 locale 都必须给全部 cultivation key，缺一即 --check 判红。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parents[2] / "apps/electron/src/renderer/../../packages/shared/src/i18n/locales"
LOCALES_DIR = Path(__file__).resolve().parents[1] / "packages/shared/src/i18n/locales"

T = {
    "zh-Hans": {
        "zenskill.cultivation.title": "修炼域",
        "zenskill.cultivation.subtitle": "和智能体一起，把成长变成看得见的回路",
        "zenskill.cultivation.loading": "读取中",
        "zenskill.cultivation.error.title": "这一块暂时读不到",
        "zenskill.cultivation.error.retry": "重试",
        "zenskill.cultivation.noDataSource.title": "这个工作区没有 ZenSkill 数据源",
        "zenskill.cultivation.noDataSource.hint": "在这个工作区里添加 ZenSkill 数据源后，这里会显示你的当前回路、今日习惯与每日一思",
        "zenskill.cultivation.hero.loop": "当前回路",
        "zenskill.cultivation.hero.loopNamed": "当前回路 · {{concept}}",
        "zenskill.cultivation.hero.active": "{{n}} 条在跑 · {{channels}} 个通道",
        "zenskill.cultivation.hero.idle": "现在没有在跑的回路 —— 去「ZenLoop」启动一轮",
        "zenskill.cultivation.section.loop": "当前回路",
        "zenskill.cultivation.section.goal": "本轮目标",
        "zenskill.cultivation.section.goalEmpty": "这一轮还没有目标 —— 去「ZenLoop」定一个",
        "zenskill.cultivation.section.actions": "进行中动作",
        "zenskill.cultivation.section.actionsEmpty": "暂无推进建议 —— 去「项目」域看待办",
        "zenskill.cultivation.section.board": "轮次看板 · 阶段分布",
        "zenskill.cultivation.section.boardEmpty": "还没有轮次 —— 去「ZenLoop」启动一轮",
        "zenskill.cultivation.section.boardLegend": "轮次状态徽章：进行中 / 还没轮到 / 已完成（沿用母题，不另造）",
        "zenskill.cultivation.section.growth": "成长 · 修炼",
        "zenskill.cultivation.growth.realm": "境界",
        "zenskill.cultivation.growth.realmNext": "{{current}} → {{next}}（还差 {{pct}}%）",
        "zenskill.cultivation.growth.realmDone": "{{current}}（已到顶）",
        "zenskill.cultivation.growth.levels": "技能等级",
        "zenskill.cultivation.growth.levelsEmpty": "还没有技能记录",
        "zenskill.cultivation.growth.energy": "能量",
        "zenskill.cultivation.growth.energyValue": "{{pct}}% · {{current}}/{{max}} 点",
        "zenskill.cultivation.growth.energyUnknown": "读不到",
        "zenskill.cultivation.card.habits.title": "今日习惯",
        "zenskill.cultivation.card.habits.empty": "今天还没有该打卡的习惯 —— 去「设置 · ZenSkill」加一个",
        "zenskill.cultivation.card.habits.footnote": "占 {{energy}} 点能量 · {{attention}} 分钟注意力",
        "zenskill.cultivation.card.thought.title": "每日一思",
        "zenskill.cultivation.card.thought.source": "《{{source}}》{{chapter}}",
        "zenskill.cultivation.card.thought.theme": "主题 · {{theme}}",
        "zenskill.cultivation.card.thought.empty": "今天没有引文",
        "zenskill.cultivation.section.advice": "同修建议",
        "zenskill.cultivation.section.adviceEmpty": "还没有建议 —— 先记一条想法或打一次卡",
        "zenskill.cultivation.section.adviceScope": "任务和行动项在「项目」域，这里只放成长与过程",
        "zenskill.cultivation.habit.checked": "已打卡",
    },
    "en": {
        "zenskill.cultivation.title": "Cultivation",
        "zenskill.cultivation.subtitle": "Grow with the agent and make the loop visible",
        "zenskill.cultivation.loading": "Loading",
        "zenskill.cultivation.error.title": "This block can't be read right now",
        "zenskill.cultivation.error.retry": "Retry",
        "zenskill.cultivation.noDataSource.title": "This workspace has no ZenSkill data source",
        "zenskill.cultivation.noDataSource.hint": "Add a ZenSkill data source to this workspace, and your current loop, today's habits and daily thought will show up here.",
        "zenskill.cultivation.hero.loop": "Current loop",
        "zenskill.cultivation.hero.loopNamed": "Current loop · {{concept}}",
        "zenskill.cultivation.hero.active": "{{n}} running · {{channels}} channels",
        "zenskill.cultivation.hero.idle": "No loop is running — start one in ZenLoop",
        "zenskill.cultivation.section.loop": "Current loop",
        "zenskill.cultivation.section.goal": "Goal of this round",
        "zenskill.cultivation.section.goalEmpty": "This round has no goal yet — set one in ZenLoop",
        "zenskill.cultivation.section.actions": "Actions in progress",
        "zenskill.cultivation.section.actionsEmpty": "No suggestions yet — check your tasks in Projects",
        "zenskill.cultivation.section.board": "Round board · stage distribution",
        "zenskill.cultivation.section.boardEmpty": "No rounds yet — start one in ZenLoop",
        "zenskill.cultivation.section.boardLegend": "Round badges: in progress / not yet / done (same motif, nothing new)",
        "zenskill.cultivation.section.growth": "Growth · cultivation",
        "zenskill.cultivation.growth.realm": "Realm",
        "zenskill.cultivation.growth.realmNext": "{{current}} → {{next}} ({{pct}}% to go)",
        "zenskill.cultivation.growth.realmDone": "{{current}} (top reached)",
        "zenskill.cultivation.growth.levels": "Skill levels",
        "zenskill.cultivation.growth.levelsEmpty": "No skill records yet",
        "zenskill.cultivation.growth.energy": "Energy",
        "zenskill.cultivation.growth.energyValue": "{{pct}}% · {{current}}/{{max}} points",
        "zenskill.cultivation.growth.energyUnknown": "unavailable",
        "zenskill.cultivation.card.habits.title": "Today's habits",
        "zenskill.cultivation.card.habits.empty": "No habit to check in today — add one in Settings · ZenSkill",
        "zenskill.cultivation.card.habits.footnote": "Uses {{energy}} energy points · {{attention}} minutes of attention",
        "zenskill.cultivation.card.thought.title": "Daily thought",
        "zenskill.cultivation.card.thought.source": "{{source}}, {{chapter}}",
        "zenskill.cultivation.card.thought.theme": "Theme · {{theme}}",
        "zenskill.cultivation.card.thought.empty": "No quote today",
        "zenskill.cultivation.section.advice": "Peer advice",
        "zenskill.cultivation.section.adviceEmpty": "No advice yet — capture a thought or check in a habit",
        "zenskill.cultivation.section.adviceScope": "Tasks and actions live in Projects; this page is for growth and process",
        "zenskill.cultivation.habit.checked": "Checked in",
    },
    "de": {
        "zenskill.cultivation.title": "Kultivation",
        "zenskill.cultivation.subtitle": "Wachs mit dem Agenten und mache den Kreislauf sichtbar",
        "zenskill.cultivation.loading": "Wird geladen",
        "zenskill.cultivation.error.title": "Dieser Abschnitt ist gerade nicht lesbar",
        "zenskill.cultivation.error.retry": "Erneut versuchen",
        "zenskill.cultivation.noDataSource.title": "Dieser Arbeitsbereich hat keine ZenSkill-Datenquelle",
        "zenskill.cultivation.noDataSource.hint": "Füge diesem Arbeitsbereich eine ZenSkill-Datenquelle hinzu — dann erscheinen hier dein aktueller Kreislauf, heutige Gewohnheiten und der Tagesgedanke.",
        "zenskill.cultivation.hero.loop": "Aktueller Kreislauf",
        "zenskill.cultivation.hero.loopNamed": "Aktueller Kreislauf · {{concept}}",
        "zenskill.cultivation.hero.active": "{{n}} laufend · {{channels}} Kanäle",
        "zenskill.cultivation.hero.idle": "Kein Kreislauf läuft — starte eine Runde in ZenLoop",
        "zenskill.cultivation.section.loop": "Aktueller Kreislauf",
        "zenskill.cultivation.section.goal": "Ziel dieser Runde",
        "zenskill.cultivation.section.goalEmpty": "Diese Runde hat noch kein Ziel — setze eines in ZenLoop",
        "zenskill.cultivation.section.actions": "Laufende Aktionen",
        "zenskill.cultivation.section.actionsEmpty": "Noch keine Vorschläge — schau in Projekte nach Aufgaben",
        "zenskill.cultivation.section.board": "Runden-Board · Verteilung nach Stufe",
        "zenskill.cultivation.section.boardEmpty": "Noch keine Runden — starte eine in ZenLoop",
        "zenskill.cultivation.section.boardLegend": "Runden-Abzeichen: läuft / noch nicht / erledigt (gleiches Motiv, nichts Neues)",
        "zenskill.cultivation.section.growth": "Wachstum · Kultivation",
        "zenskill.cultivation.growth.realm": "Realm",
        "zenskill.cultivation.growth.realmNext": "{{current}} → {{next}} (noch {{pct}}%)",
        "zenskill.cultivation.growth.realmDone": "{{current}} (Höchststand erreicht)",
        "zenskill.cultivation.growth.levels": "Fertigkeitsstufen",
        "zenskill.cultivation.growth.levelsEmpty": "Noch keine Fertigkeitsdaten",
        "zenskill.cultivation.growth.energy": "Energie",
        "zenskill.cultivation.growth.energyValue": "{{pct}}% · {{current}}/{{max}} Punkte",
        "zenskill.cultivation.growth.energyUnknown": "nicht lesbar",
        "zenskill.cultivation.card.habits.title": "Heutige Gewohnheiten",
        "zenskill.cultivation.card.habits.empty": "Heute gibt es nichts zu bestätigen — lege eine in Einstellungen · ZenSkill an",
        "zenskill.cultivation.card.habits.footnote": "Belegt {{energy}} Energiepunkte · {{attention}} Minuten Aufmerksamkeit",
        "zenskill.cultivation.card.thought.title": "Tagesgedanke",
        "zenskill.cultivation.card.thought.source": "{{source}}, {{chapter}}",
        "zenskill.cultivation.card.thought.theme": "Thema · {{theme}}",
        "zenskill.cultivation.card.thought.empty": "Heute kein Zitat",
        "zenskill.cultivation.section.advice": "Rat des Gefährten",
        "zenskill.cultivation.section.adviceEmpty": "Noch kein Rat — notiere eine Idee oder bestätige eine Gewohnheit",
        "zenskill.cultivation.section.adviceScope": "Aufgaben und Aktionen stehen im Bereich „Projekte“ — hier geht es um Wachstum und Prozess",
        "zenskill.cultivation.habit.checked": "Bestätigt",
    },
    "es": {
        "zenskill.cultivation.title": "Cultivo",
        "zenskill.cultivation.subtitle": "Crece junto al agente y haz visible el ciclo",
        "zenskill.cultivation.loading": "Cargando",
        "zenskill.cultivation.error.title": "Este bloque no se puede leer ahora",
        "zenskill.cultivation.error.retry": "Reintentar",
        "zenskill.cultivation.noDataSource.title": "Este espacio de trabajo no tiene fuente de datos de ZenSkill",
        "zenskill.cultivation.noDataSource.hint": "Añade una fuente de datos de ZenSkill a este espacio de trabajo y aquí aparecerán tu ciclo actual, hábitos de hoy y el pensamiento del día.",
        "zenskill.cultivation.hero.loop": "Ciclo actual",
        "zenskill.cultivation.hero.loopNamed": "Ciclo actual · {{concept}}",
        "zenskill.cultivation.hero.active": "{{n}} en marcha · {{channels}} canales",
        "zenskill.cultivation.hero.idle": "No hay ningún ciclo en marcha — empieza uno en ZenLoop",
        "zenskill.cultivation.section.loop": "Ciclo actual",
        "zenskill.cultivation.section.goal": "Objetivo de esta ronda",
        "zenskill.cultivation.section.goalEmpty": "Esta ronda aún no tiene objetivo — define uno en ZenLoop",
        "zenskill.cultivation.section.actions": "Acciones en curso",
        "zenskill.cultivation.section.actionsEmpty": "Sin sugerencias todavía — revisa tus tareas en Proyectos",
        "zenskill.cultivation.section.board": "Tablero de rondas · distribución por etapa",
        "zenskill.cultivation.section.boardEmpty": "Aún no hay rondas — empieza una en ZenLoop",
        "zenskill.cultivation.section.boardLegend": "Insignias de ronda: en curso / pendiente / completada (el mismo motivo, nada nuevo)",
        "zenskill.cultivation.section.growth": "Crecimiento · cultivo",
        "zenskill.cultivation.growth.realm": "Nivel",
        "zenskill.cultivation.growth.realmNext": "{{current}} → {{next}} (falta {{pct}}%)",
        "zenskill.cultivation.growth.realmDone": "{{current}} (máximo alcanzado)",
        "zenskill.cultivation.growth.levels": "Niveles de habilidad",
        "zenskill.cultivation.growth.levelsEmpty": "Aún no hay registros de habilidades",
        "zenskill.cultivation.growth.energy": "Energía",
        "zenskill.cultivation.growth.energyValue": "{{pct}}% · {{current}}/{{max}} puntos",
        "zenskill.cultivation.growth.energyUnknown": "no disponible",
        "zenskill.cultivation.card.habits.title": "Hábitos de hoy",
        "zenskill.cultivation.card.habits.empty": "Hoy no hay hábitos que registrar — añade uno en Ajustes · ZenSkill",
        "zenskill.cultivation.card.habits.footnote": "Ocupa {{energy}} puntos de energía · {{attention}} minutos de atención",
        "zenskill.cultivation.card.thought.title": "Pensamiento del día",
        "zenskill.cultivation.card.thought.source": "{{source}}, {{chapter}}",
        "zenskill.cultivation.card.thought.theme": "Tema · {{theme}}",
        "zenskill.cultivation.card.thought.empty": "Hoy no hay cita",
        "zenskill.cultivation.section.advice": "Consejo del compañero",
        "zenskill.cultivation.section.adviceEmpty": "Todavía no hay consejos — anota una idea o registra un hábito",
        "zenskill.cultivation.section.adviceScope": "Las tareas y acciones están en «Proyectos»; aquí solo hay crecimiento y proceso",
        "zenskill.cultivation.habit.checked": "Registrado",
    },
    "hu": {
        "zenskill.cultivation.title": "Kultiváció",
        "zenskill.cultivation.subtitle": "Növekedj az ügynökkel, és tedd láthatóvá a kört",
        "zenskill.cultivation.loading": "Betöltés",
        "zenskill.cultivation.error.title": "Ezt a blokkot most nem lehet olvasni",
        "zenskill.cultivation.error.retry": "Újra",
        "zenskill.cultivation.noDataSource.title": "Ennek a munkaterületnek nincs ZenSkill adatforrása",
        "zenskill.cultivation.noDataSource.hint": "Adj meg egy ZenSkill adatforrást ehhez a munkaterülethez, és itt megjelennek az aktuális kör, a mai szokások és a napi gondolat.",
        "zenskill.cultivation.hero.loop": "Aktuális kör",
        "zenskill.cultivation.hero.loopNamed": "Aktuális kör · {{concept}}",
        "zenskill.cultivation.hero.active": "{{n}} fut · {{channels}} csatorna",
        "zenskill.cultivation.hero.idle": "Nincs futó kör — indíts egyet a ZenLoopban",
        "zenskill.cultivation.section.loop": "Aktuális kör",
        "zenskill.cultivation.section.goal": "A kör célja",
        "zenskill.cultivation.section.goalEmpty": "Ennek a körnek még nincs célja — adj meg egyet a ZenLoopban",
        "zenskill.cultivation.section.actions": "Folyamatban lévő műveletek",
        "zenskill.cultivation.section.actionsEmpty": "Még nincs javaslat — nézd meg a teendőket a „Projektek” területen",
        "zenskill.cultivation.section.board": "Kör-lepény · szakaszok megoszlása",
        "zenskill.cultivation.section.boardEmpty": "Még nincs kör — indíts egyet a ZenLoopban",
        "zenskill.cultivation.section.boardLegend": "Kör-jelvények: folyamatban / még nem / kész (ugyanaz a motívum, semmi új)",
        "zenskill.cultivation.section.growth": "Növekedés · kultiváció",
        "zenskill.cultivation.growth.realm": "Szint",
        "zenskill.cultivation.growth.realmNext": "{{current}} → {{next}} (még {{pct}}%)",
        "zenskill.cultivation.growth.realmDone": "{{current}} (elérve)",
        "zenskill.cultivation.growth.levels": "Készségszintek",
        "zenskill.cultivation.growth.levelsEmpty": "Még nincs készségadat",
        "zenskill.cultivation.growth.energy": "Energia",
        "zenskill.cultivation.growth.energyValue": "{{pct}}% · {{current}}/{{max}} pont",
        "zenskill.cultivation.growth.energyUnknown": "nem olvasható",
        "zenskill.cultivation.card.habits.title": "Mai szokások",
        "zenskill.cultivation.card.habits.empty": "Ma nincs megerősítendő szokás — vegyél fel egyet a Beállítások · ZenSkill alatt",
        "zenskill.cultivation.card.habits.footnote": "{{energy}} energiapontot · {{attention}} perc figyelmet foglal",
        "zenskill.cultivation.card.thought.title": "Napi gondolat",
        "zenskill.cultivation.card.thought.source": "{{source}}, {{chapter}}",
        "zenskill.cultivation.card.thought.theme": "Téma · {{theme}}",
        "zenskill.cultivation.card.thought.empty": "Ma nincs idézet",
        "zenskill.cultivation.section.advice": "Társ tanácsa",
        "zenskill.cultivation.section.adviceEmpty": "Még nincs tanács — jegyezz fel egy ötletet vagy erősíts meg egy szokást",
        "zenskill.cultivation.section.adviceScope": "A feladatok és műveletek a „Projektek” területen vannak — itt növekedés és folyamat van",
        "zenskill.cultivation.habit.checked": "Megerősítve",
    },
    "ja": {
        "zenskill.cultivation.title": "修養",
        "zenskill.cultivation.subtitle": "エージェントと 함께成長し、ループを見える形に",
        "zenskill.cultivation.loading": "読み込み中",
        "zenskill.cultivation.error.title": "このブロックは一時的に読み取れません",
        "zenskill.cultivation.error.retry": "再試行",
        "zenskill.cultivation.noDataSource.title": "このワークスペースには ZenSkill データソースがありません",
        "zenskill.cultivation.noDataSource.hint": "このワークスペースに ZenSkill データソースを追加すると、現在のループ・今日の習慣・今日の一思がここに表示されます。",
        "zenskill.cultivation.hero.loop": "現在のループ",
        "zenskill.cultivation.hero.loopNamed": "現在のループ · {{concept}}",
        "zenskill.cultivation.hero.active": "{{n}} 件進行中 · {{channels}} チャンネル",
        "zenskill.cultivation.hero.idle": "実行中のループはありません — ZenLoop で 1 輪始めましょう",
        "zenskill.cultivation.section.loop": "現在のループ",
        "zenskill.cultivation.section.goal": "このラウンドの目標",
        "zenskill.cultivation.section.goalEmpty": "このラウンドの目標はまだありません — ZenLoop で設定しましょう",
        "zenskill.cultivation.section.actions": "進行中のアクション",
        "zenskill.cultivation.section.actionsEmpty": "提案はまだありません — 「プロジェクト」で ToDo を確認しましょう",
        "zenskill.cultivation.section.board": "ラウンドボード · 段階の分布",
        "zenskill.cultivation.section.boardEmpty": "まだラウンドがありません — ZenLoop で 1 輪始めましょう",
        "zenskill.cultivation.section.boardLegend": "ラウンドのバッジ：進行中 / まだ / 完了（既存の図柄を使い、新しく作りません）",
        "zenskill.cultivation.section.growth": "成長 · 修養",
        "zenskill.cultivation.growth.realm": "境位",
        "zenskill.cultivation.growth.realmNext": "{{current}} → {{next}}（あと {{pct}}%）",
        "zenskill.cultivation.growth.realmDone": "{{current}}（到達済み）",
        "zenskill.cultivation.growth.levels": "スキル等級",
        "zenskill.cultivation.growth.levelsEmpty": "スキル記録がまだありません",
        "zenskill.cultivation.growth.energy": "エネルギー",
        "zenskill.cultivation.growth.energyValue": "{{pct}}% · {{current}}/{{max}} ポイント",
        "zenskill.cultivation.growth.energyUnknown": "読み取れません",
        "zenskill.cultivation.card.habits.title": "今日の習慣",
        "zenskill.cultivation.card.habits.empty": "今日チェックインする習慣がありません — 「設定 · ZenSkill」で追加しましょう",
        "zenskill.cultivation.card.habits.footnote": "エネルギー {{energy}} ポイント · 集中時間 {{attention}} 分",
        "zenskill.cultivation.card.thought.title": "今日の一思",
        "zenskill.cultivation.card.thought.source": "《{{source}}》{{chapter}}",
        "zenskill.cultivation.card.thought.theme": "テーマ · {{theme}}",
        "zenskill.cultivation.card.thought.empty": "今日は引用がありません",
        "zenskill.cultivation.section.advice": "仲間の助言",
        "zenskill.cultivation.section.adviceEmpty": "まだ助言がありません — 考えを記録するか習慣にチェックインしましょう",
        "zenskill.cultivation.section.adviceScope": "タスクとアクションは「プロジェクト」域にあります。ここでは成長と過程だけを示します",
        "zenskill.cultivation.habit.checked": "チェックインしました",
    },
    "pl": {
        "zenskill.cultivation.title": "Kultywacja",
        "zenskill.cultivation.subtitle": "Rośnij razem z agentem i uczyń pętlę widoczną",
        "zenskill.cultivation.loading": "Ładowanie",
        "zenskill.cultivation.error.title": "Tego bloku nie da się teraz odczytać",
        "zenskill.cultivation.error.retry": "Spróbuj ponownie",
        "zenskill.cultivation.noDataSource.title": "Ten obszar roboczy nie ma źródła danych ZenSkill",
        "zenskill.cultivation.noDataSource.hint": "Dodaj źródło danych ZenSkill do tego obszaru roboczego, a pojawią się tutaj bieżąca pętla, dzisiejsze nawyki i myśl dnia.",
        "zenskill.cultivation.hero.loop": "Bieżąca pętla",
        "zenskill.cultivation.hero.loopNamed": "Bieżąca pętla · {{concept}}",
        "zenskill.cultivation.hero.active": "{{n}} w toku · {{channels}} kanałów",
        "zenskill.cultivation.hero.idle": "Żadna pętla nie działa — uruchom jedną w ZenLoop",
        "zenskill.cultivation.section.loop": "Bieżąca pętla",
        "zenskill.cultivation.section.goal": "Cel tej rundy",
        "zenskill.cultivation.section.goalEmpty": "Ta runda nie ma jeszcze celu — ustaw go w ZenLoop",
        "zenskill.cultivation.section.actions": "Działania w toku",
        "zenskill.cultivation.section.actionsEmpty": "Brak sugestii — sprawdź zadania w Projektach",
        "zenskill.cultivation.section.board": "Tablica rund · podział etapów",
        "zenskill.cultivation.section.boardEmpty": "Nie ma jeszcze rund — uruchom jedną w ZenLoop",
        "zenskill.cultivation.section.boardLegend": "Odznaki rundy: w toku / jeszcze nie / ukończona (ten sam motyw, nic nowego)",
        "zenskill.cultivation.section.growth": "Wzrost · kultywacja",
        "zenskill.cultivation.growth.realm": "Poziom",
        "zenskill.cultivation.growth.realmNext": "{{current}} → {{next}} (brakuje {{pct}}%)",
        "zenskill.cultivation.growth.realmDone": "{{current}} (osiągnięto)",
        "zenskill.cultivation.growth.levels": "Poziomy umiejętności",
        "zenskill.cultivation.growth.levelsEmpty": "Brak zapisów umiejętności",
        "zenskill.cultivation.growth.energy": "Energia",
        "zenskill.cultivation.growth.energyValue": "{{pct}}% · {{current}}/{{max}} punktów",
        "zenskill.cultivation.growth.energyUnknown": "nieczytelne",
        "zenskill.cultivation.card.habits.title": "Dzisiejsze nawyki",
        "zenskill.cultivation.card.habits.empty": "Dziś nie ma nawyku do odhaczenia — dodaj go w Ustawieniach · ZenSkill",
        "zenskill.cultivation.card.habits.footnote": "Zajmuje {{energy}} punktów energii · {{attention}} minut uwagi",
        "zenskill.cultivation.card.thought.title": "Myśl dnia",
        "zenskill.cultivation.card.thought.source": "{{source}}, {{chapter}}",
        "zenskill.cultivation.card.thought.theme": "Motyw · {{theme}}",
        "zenskill.cultivation.card.thought.empty": "Dziś brak cytatu",
        "zenskill.cultivation.section.advice": "Rada towarzysza",
        "zenskill.cultivation.section.adviceEmpty": "Jeszcze brak rady — zapisz myśl lub odznacz nawyk",
        "zenskill.cultivation.section.adviceScope": "Zadania i działania są w dziale „Projekty” — tu są tylko wzrost i proces",
        "zenskill.cultivation.habit.checked": "Odhaczone",
    },
}

# ── 人称模式设置（第十八批 D 段 D2-4）──────────────────────────────
SETTINGS_KEYS = {'zh-Hans': {'settings.zenskill.title': 'ZenSkill', 'settings.zenskill.description': '智能体的口吻与称呼', 'settings.zenskill.noWorkspace': '没有活动工作区 —— 先打开一个工作区', 'settings.zenskill.readFailed': '读不到人称模式', 'settings.zenskill.switched': '已切换到「{{name}}」', 'settings.zenskill.switchFailed': '切换失败', 'settings.zenskill.persona.title': '人称模式', 'settings.zenskill.persona.description': '只改智能体说话的口吻，不改它的称呼 —— 称呼恒为「智能体」。', 'settings.zenskill.persona.empty': '读不到可选模式', 'settings.zenskill.persona.voice': '口吻', 'settings.zenskill.persona.sample': '示例', 'settings.zenskill.persona.adviceLine': '修炼域 · 同修建议', 'settings.zenskill.term.title': '称呼', 'settings.zenskill.term.description': '智能体只有一个称呼，三种模式都不换。', 'settings.zenskill.term.label': '对智能体的称呼', 'settings.zenskill.term.default': '智能体'}, 'en': {'settings.zenskill.title': 'ZenSkill', 'settings.zenskill.description': 'How the agent speaks and what it is called', 'settings.zenskill.noWorkspace': 'No active workspace — open one first', 'settings.zenskill.readFailed': "Can't read the persona mode", 'settings.zenskill.switched': 'Switched to “{{name}}”', 'settings.zenskill.switchFailed': 'Switch failed', 'settings.zenskill.persona.title': 'Persona mode', 'settings.zenskill.persona.description': "Only the agent's tone changes — the way it is called stays the same.", 'settings.zenskill.persona.empty': 'No modes available', 'settings.zenskill.persona.voice': 'Tone', 'settings.zenskill.persona.sample': 'Sample', 'settings.zenskill.persona.adviceLine': 'Cultivation · peer advice', 'settings.zenskill.term.title': 'Name', 'settings.zenskill.term.description': 'The agent has one name; no mode changes it.', 'settings.zenskill.term.label': 'What the agent is called', 'settings.zenskill.term.default': 'the agent'}, 'de': {'settings.zenskill.title': 'ZenSkill', 'settings.zenskill.description': 'Ton und Name des Agenten', 'settings.zenskill.noWorkspace': 'Kein aktiver Arbeitsbereich — öffne zuerst einen', 'settings.zenskill.readFailed': 'Persona-Modus nicht lesbar', 'settings.zenskill.switched': 'Zu „{{name}}“ gewechselt', 'settings.zenskill.switchFailed': 'Wechsel fehlgeschlagen', 'settings.zenskill.persona.title': 'Persona-Modus', 'settings.zenskill.persona.description': 'Nur der Ton des Agenten ändert sich — wie er heißt, bleibt gleich.', 'settings.zenskill.persona.empty': 'Keine Modi verfügbar', 'settings.zenskill.persona.voice': 'Ton', 'settings.zenskill.persona.sample': 'Beispiel', 'settings.zenskill.persona.adviceLine': 'Kultivation · Rat des Gefährten', 'settings.zenskill.term.title': 'Name', 'settings.zenskill.term.description': 'Der Agent hat einen Namen; kein Modus ändert ihn.', 'settings.zenskill.term.label': 'Wie der Agent heißt', 'settings.zenskill.term.default': 'der Agent'}, 'es': {'settings.zenskill.title': 'ZenSkill', 'settings.zenskill.description': 'El tono y el nombre del agente', 'settings.zenskill.noWorkspace': 'No hay espacio de trabajo activo — abre uno primero', 'settings.zenskill.readFailed': 'No se puede leer el modo de persona', 'settings.zenskill.switched': 'Cambiado a «{{name}}»', 'settings.zenskill.switchFailed': 'No se pudo cambiar', 'settings.zenskill.persona.title': 'Modo de persona', 'settings.zenskill.persona.description': 'Solo cambia el tono del agente; cómo se llama no cambia.', 'settings.zenskill.persona.empty': 'No hay modos disponibles', 'settings.zenskill.persona.voice': 'Tono', 'settings.zenskill.persona.sample': 'Ejemplo', 'settings.zenskill.persona.adviceLine': 'Cultivo · consejo del compañero', 'settings.zenskill.term.title': 'Nombre', 'settings.zenskill.term.description': 'El agente tiene un solo nombre; ningún modo lo cambia.', 'settings.zenskill.term.label': 'Cómo se llama al agente', 'settings.zenskill.term.default': 'el agente'}, 'hu': {'settings.zenskill.title': 'ZenSkill', 'settings.zenskill.description': 'Az ügynök hangja és neve', 'settings.zenskill.noWorkspace': 'Nincs aktív munkaterület — előbb nyiss egyet', 'settings.zenskill.readFailed': 'A persona mód nem olvasható', 'settings.zenskill.switched': 'Átállva: „{{name}}”', 'settings.zenskill.switchFailed': 'A váltás nem sikerült', 'settings.zenskill.persona.title': 'Persona mód', 'settings.zenskill.persona.description': 'Csak az ügynök hangja változik — a neve nem.', 'settings.zenskill.persona.empty': 'Nincs elérhető mód', 'settings.zenskill.persona.voice': 'Hangnem', 'settings.zenskill.persona.sample': 'Példa', 'settings.zenskill.persona.adviceLine': 'Kultiváció · társ tanácsa', 'settings.zenskill.term.title': 'Név', 'settings.zenskill.term.description': 'Az ügynöknek egy neve van; egyetlen mód sem változtatja meg.', 'settings.zenskill.term.label': 'Ahogy az ügynököt hívják', 'settings.zenskill.term.default': 'az ügynök'}, 'ja': {'settings.zenskill.title': 'ZenSkill', 'settings.zenskill.description': 'エージェントの話し方と呼び名', 'settings.zenskill.noWorkspace': 'アクティブなワークスペースがありません — 先に開いてください', 'settings.zenskill.readFailed': '人称モードを読み取れません', 'settings.zenskill.switched': '「{{name}}」に切り替えました', 'settings.zenskill.switchFailed': '切り替えに失敗しました', 'settings.zenskill.persona.title': '人称モード', 'settings.zenskill.persona.description': '変わるのは話し方だけ。呼び名は変えません。', 'settings.zenskill.persona.empty': '利用できるモードがありません', 'settings.zenskill.persona.voice': '話し方', 'settings.zenskill.persona.sample': '例', 'settings.zenskill.persona.adviceLine': '修養 · 仲間の助言', 'settings.zenskill.term.title': '呼び名', 'settings.zenskill.term.description': 'エージェントの呼び名はひとつ。モードで変わりません。', 'settings.zenskill.term.label': 'エージェントの呼び名', 'settings.zenskill.term.default': 'エージェント'}, 'pl': {'settings.zenskill.title': 'ZenSkill', 'settings.zenskill.description': 'Ton i nazwa agenta', 'settings.zenskill.noWorkspace': 'Brak aktywnego obszaru roboczego — najpierw go otwórz', 'settings.zenskill.readFailed': 'Nie da się odczytać trybu osoby', 'settings.zenskill.switched': 'Przełączono na „{{name}}”', 'settings.zenskill.switchFailed': 'Przełączenie nie powiodło się', 'settings.zenskill.persona.title': 'Tryb osoby', 'settings.zenskill.persona.description': 'Zmienia się tylko ton agenta — nazwa pozostaje ta sama.', 'settings.zenskill.persona.empty': 'Brak dostępnych trybów', 'settings.zenskill.persona.voice': 'Ton', 'settings.zenskill.persona.sample': 'Przykład', 'settings.zenskill.persona.adviceLine': 'Kultywacja · rada towarzysza', 'settings.zenskill.term.title': 'Nazwa', 'settings.zenskill.term.description': 'Agent ma jedną nazwę; żaden tryb jej nie zmienia.', 'settings.zenskill.term.label': 'Jak nazywa się agenta', 'settings.zenskill.term.default': 'agenta'}}

for _loc, _kv in SETTINGS_KEYS.items():
    T[_loc].update(_kv)


def dump(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    check = "--check" in sys.argv
    expected = set(T["zh-Hans"])
    bad = 0
    for loc, table in T.items():
        path = LOCALES_DIR / f"{loc}.json"
        if set(table) != expected:
            print(f"[FAIL] {loc}: key 集合与 zh-Hans 不一致")
            bad += 1
        data = json.loads(path.read_text(encoding="utf-8"))
        missing = expected - set(data)
        if missing:
            print(f"[FAIL] {loc}: 缺 {len(missing)} 个 cultivation key")
            bad += 1
        merged = {**data, **table}
        if check:
            expected_text = dump(merged)
            actual_text = path.read_text(encoding="utf-8")
            if actual_text != expected_text:
                print(f"[FAIL] {loc}: 文件内容与预期不一致（--check 判红）")
                bad += 1
        else:
            path.write_text(dump(merged), encoding="utf-8")
            print(f"[OK] {loc}: 写入 {len(table)} 个 cultivation key（共 {len(merged)}）")
    # 全 locale key 集合一致性
    sets = {}
    for loc in T:
        data = json.loads((LOCALES_DIR / f"{loc}.json").read_text(encoding="utf-8"))
        sets[loc] = set(data)
    base = sets["zh-Hans"]
    for loc, s in sets.items():
        if s != base:
            print(f"[FAIL] {loc}: 与 zh-Hans 的 key 集合不一致（缺 {len(base - s)} / 多 {len(s - base)}）")
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
