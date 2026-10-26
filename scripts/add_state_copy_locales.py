#!/usr/bin/env python3
"""补五态文案（第十九批 B 段）—— 给 7 个 locale 写回「空态必给下一步动作」的版本。

用法：python3 add_state_copy_locales.py [--check]

★ 为什么要有这个脚本
-------------------
第十八批 D3 落五态实例时暴露：五态文案**没有真相源**（`copy_terminology.json`
至今没有 `stateCopy` 段）⇒ 各页各写一套 ⇒ 实测 32 条空态里 **22 条**只写
「暂无X」这种**纯状态陈述**，不给用户任何下一步动作。

★ 本脚本只做「**写文案**」；口径真相源在主仓 `specs/design/copy_terminology.json`
  的 `stateCopy` 段，门禁是主仓的 `scripts/check_state_copy_wiring.py`
  （逐字一致 + 漏登记 + 空态无动作 三条判据）。

★ 格式纪律：locales/*.json 是 `json.dumps(..., ensure_ascii=False, indent=2,
  sort_keys=True) + "\n"` ⇒ 本脚本按同一口径写回，**不重排、不改别的 key**。
★ 口径纪律：7 个 locale **key 集合必须完全一致**，每个 locale 都要给全部条目。
★ 破折号惯例：中文用「——」，其余语言用「—」。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

LOCALES_DIR = Path(__file__).resolve().parents[1] / "packages/shared/src/i18n/locales"

# ── 本批要写的文案（22 条空态改写 + 2 条英文中文残留 + 9 条德语拉丁转写）──
T: dict[str, dict[str, str]] = {
    "zh-Hans": {
        "zenskill.collaboration.statsEmpty": "还没有技能统计 —— 再装一个技能就能看到",
        "zenskill.collaboration.transferEmpty": "暂无可迁移模式 —— 同一个技能用得够久就会出现",
        "zenskill.cultivation.card.thought.empty": "引文库暂时读不到 —— 稍后再来看看",
        "zenskill.cultivation.growth.levelsEmpty": "还没有技能等级 —— 去「技能」域记录一次使用",
        "zenskill.gtd.actions.empty": "暂无待办行动 —— 去「收件箱」挑一件推进",
        "zenskill.gtd.calendar.dayActionsEmpty": "当天没有到期行动 —— 加一条今天的日程试试",
        "zenskill.gtd.calendar.dayEmpty": "当天暂无日程 —— 加一条日程试试",
        "zenskill.gtd.calendar.empty": "今日无事件 —— 加一条日程试试",
        "zenskill.gtd.calendar.suggestEmpty": "暂无可用建议 —— 写下这周要做的事试试",
        "zenskill.gtd.inbox.empty": "暂无待处理项 —— 记一条想法试试",
        "zenskill.gtd.incubating.empty": "暂无孵化中的条目 —— 先记一条想法试试",
        "zenskill.gtd.projects.actionsEmpty": "暂无进行中的行动 —— 从项目里挑一件推进",
        "zenskill.gtd.projects.empty": "暂无进行中的项目 —— 新建一个项目试试",
        "zenskill.insights.empty": "没有匹配筛选条件的洞察 —— 换个条件看看",
        "zenskill.market.empty": "暂无结果 —— 换个关键词搜搜",
        "zenskill.memory.empty": "暂无记忆 —— 聊两句，让智能体记住你",
        "zenskill.panel.goals.empty": "暂无目标 —— 定一个目标试试",
        "zenskill.panel.memory.empty": "暂无记忆 —— 聊两句，让智能体记住你",
        "zenskill.profile.goals.empty": "暂无活跃目标 —— 定一个目标试试",
        "zenskill.profile.habitsEmpty": "暂无习惯数据 —— 在「设置 · ZenSkill」加一个习惯",
        "zenskill.skillGraph.empty": "暂无技能数据 —— 装一个技能试试",
        "zenskill.skillGraph.emptyDomain": "该域暂无技能 —— 装一个技能试试",
        "zenskill.toast.captured": "已捕获",
        "zenskill.collaboration.gap": "差距:",
        "zenskill.collaboration.overview": "生态概览",
        "zenskill.collaboration.transfer": "可迁移模式",
        "zenskill.collaboration.insights": "跨技能洞察",
        "zenskill.session.empty": "还没有会话 —— 新建一个试试",
        "zenskill.state.loading": "读取中",
        "zenskill.state.error.title": "这一块暂时读不到",
        "zenskill.state.error.retry": "重试",
        "zenskill.state.noAccess.title": "这个工作区没有 ZenSkill 数据源",
        "zenskill.state.noAccess.hint": "在这个工作区里添加 ZenSkill 数据源后，这里会显示成长与过程的读数",
        "zenskill.readout.loop": "轮次",
        "zenskill.readout.loopCount": "{n} 条在跑",
        "zenskill.readout.energy": "能量",
        "zenskill.readout.attention": "注意力",
        "zenskill.readout.atMost": "至多",
        "zenskill.readout.attentionUpperHint": "近期深度占用暂时读不到，此值为上限",
        "zenskill.unit.point": "点",
        "zenskill.unit.minute": "分钟",
        "zenskill.readout.delegation": "智能体承担",
        "zenskill.readout.delegationHint": "{n} / {total} 项由智能体接下",
        "zenskill.readout.energyRecovering": "恢复中 +{n} 点",
        "zenskill.profile.understandingError": "基于 {n} 个样本 · 误差范围 ±{e} 分",
    },
    "en": {
        "zenskill.collaboration.statsEmpty": "No skill statistics yet — install one more skill to see them",
        "zenskill.collaboration.transferEmpty": "No transferable patterns yet — they appear once you keep using a skill",
        "zenskill.cultivation.card.thought.empty": "The quote library can't be read right now — come back later",
        "zenskill.cultivation.growth.levelsEmpty": "No skill levels yet — record a skill use in the Skills area",
        "zenskill.gtd.actions.empty": "No pending actions — pick one from the Inbox",
        "zenskill.gtd.calendar.dayActionsEmpty": "Nothing due this day — add an event for today",
        "zenskill.gtd.calendar.dayEmpty": "No events on this day — add one",
        "zenskill.gtd.calendar.empty": "No events today — add one",
        "zenskill.gtd.calendar.suggestEmpty": "No suggestions available — write down what to do this week",
        "zenskill.gtd.inbox.empty": "Nothing pending — capture an idea",
        "zenskill.gtd.incubating.empty": "Nothing incubating — capture an idea first",
        "zenskill.gtd.projects.actionsEmpty": "No open actions — pick one from a project",
        "zenskill.gtd.projects.empty": "No active projects — create one",
        "zenskill.insights.empty": "No insights match the filters — try another filter",
        "zenskill.market.empty": "No results — search with another keyword",
        "zenskill.memory.empty": "No memories yet — chat a little so the agent can remember you",
        "zenskill.panel.goals.empty": "No goals yet — set one",
        "zenskill.panel.memory.empty": "No memories stored — chat a little so the agent can remember you",
        "zenskill.profile.goals.empty": "No active goals — set one",
        "zenskill.profile.habitsEmpty": "No habit data yet — add a habit in Settings · ZenSkill",
        "zenskill.skillGraph.empty": "No skill data yet — install a skill",
        "zenskill.skillGraph.emptyDomain": "No skills in this domain — install one",
        # ★ 中文残留（本批实测：英文 locale 里这条还是中文）
        "zenskill.toast.captured": "Captured",
        "zenskill.collaboration.gap": "Gap:",
        "zenskill.collaboration.overview": "Ecosystem Overview",
        "zenskill.collaboration.transfer": "Transferable Patterns",
        "zenskill.collaboration.insights": "Cross-Skill Insights",
        "zenskill.session.empty": "No session yet — create one",
        "zenskill.state.loading": "Loading",
        "zenskill.state.error.title": "This block can't be read right now",
        "zenskill.state.error.retry": "Retry",
        "zenskill.state.noAccess.title": "This workspace has no ZenSkill data source",
        "zenskill.state.noAccess.hint": "Add a ZenSkill data source to this workspace, and growth and process readouts will show up here",
        "zenskill.readout.loop": "Loop",
        "zenskill.readout.loopCount": "{n} running",
        "zenskill.readout.energy": "Energy",
        "zenskill.readout.attention": "Attention",
        "zenskill.readout.atMost": "at most",
        "zenskill.readout.attentionUpperHint": "Recent focus usage can't be read right now — this value is an upper bound",
        "zenskill.unit.point": "points",
        "zenskill.unit.minute": "minutes",
        "zenskill.readout.delegation": "Agent handles",
        "zenskill.readout.delegationHint": "{n} of {total} handled by the agent",
        "zenskill.readout.energyRecovering": "recovering +{n} pts",
        "zenskill.profile.understandingError": "Based on {n} samples · error range ±{e}",
    },
    "de": {
        "zenskill.collaboration.statsEmpty": "Noch keine Skill-Statistiken — installiere eine weitere Skill, um sie zu sehen",
        "zenskill.collaboration.transferEmpty": "Noch keine übertragbaren Muster — sie erscheinen, sobald du einen Skill lange nutzt",
        "zenskill.cultivation.card.thought.empty": "Die Zitatbibliothek ist gerade nicht lesbar — schau später nochmal vorbei",
        "zenskill.cultivation.growth.levelsEmpty": "Noch keine Fertigkeitsstufen — nutze eine Skill einmal im Bereich „Skills“",
        "zenskill.gtd.actions.empty": "Keine offenen Aktionen — wähle eine aus dem Eingang",
        "zenskill.gtd.calendar.dayActionsEmpty": "An diesem Tag nichts fällig — trag einen Termin für heute ein",
        "zenskill.gtd.calendar.dayEmpty": "An diesem Tag keine Termine — trag einen ein",
        "zenskill.gtd.calendar.empty": "Heute keine Termine — trag einen ein",
        "zenskill.gtd.calendar.suggestEmpty": "Keine Vorschläge verfügbar — notiere, was diese Woche zu tun ist",
        "zenskill.gtd.inbox.empty": "Nichts offen — fange einen Gedanken ab",
        "zenskill.gtd.incubating.empty": "Nichts in der Inkubation — fange zuerst einen Gedanken ab",
        "zenskill.gtd.projects.actionsEmpty": "Keine offenen Aktionen — wähle eine aus einem Projekt",
        "zenskill.gtd.projects.empty": "Keine aktiven Projekte — leg eine an",
        "zenskill.insights.empty": "Keine Einblicke für die gewählten Filter — probiere einen anderen Filter",
        "zenskill.market.empty": "Keine Ergebnisse — suche mit einem anderen Stichwort",
        "zenskill.memory.empty": "Noch keine Erinnerungen — chatte ein bisschen, damit der Agent dich kennenlernt",
        "zenskill.panel.goals.empty": "Keine Ziele — setze eines",
        "zenskill.panel.memory.empty": "Keine Erinnerungen gespeichert — chatte ein bisschen, damit der Agent dich kennenlernt",
        "zenskill.profile.goals.empty": "Keine aktiven Ziele — setze eines",
        "zenskill.profile.habitsEmpty": "Noch keine Gewohnheitsdaten — lege unter Einstellungen · ZenSkill eine Gewohnheit an",
        "zenskill.skillGraph.empty": "Noch keine Skill-Daten — installiere eine Skill",
        "zenskill.skillGraph.emptyDomain": "Keine Skills in dieser Domäne — installiere eine",
        # ★ 拉丁转写（ue/oe/ae ⇒ ��/ö/ä）：本 locale 其它新文案用的是真变音符
        "zenskill.collaboration.gap": "Lücke:",
        "zenskill.collaboration.overview": "Ökosystem-Übersicht",
        "zenskill.collaboration.transfer": "Übertragbare Muster",
        "zenskill.collaboration.insights": "Skill-übergreifende Erkenntnisse",
        "zenskill.toast.captured": "Erfasst",
        "zenskill.session.empty": "Noch keine Sitzung — leg eine an",
        "zenskill.state.loading": "Lädt",
        "zenskill.state.error.title": "Dieser Abschnitt ist gerade nicht lesbar",
        "zenskill.state.error.retry": "Erneut versuchen",
        "zenskill.state.noAccess.title": "Dieser Arbeitsbereich hat keine ZenSkill-Datenquelle",
        "zenskill.state.noAccess.hint": "Füge diesem Arbeitsbereich eine ZenSkill-Datenquelle hinzu — dann erscheinen hier Fortschritts- und Prozesswerte",
        "zenskill.readout.loop": "Kreislauf",
        "zenskill.readout.loopCount": "{n} laufend",
        "zenskill.readout.energy": "Energie",
        "zenskill.readout.attention": "Aufmerksamkeit",
        "zenskill.readout.atMost": "höchstens",
        "zenskill.readout.attentionUpperHint": "Die jüngste Fokusnutzung ist gerade nicht lesbar — dieser Wert ist eine Obergrenze",
        "zenskill.unit.point": "Punkte",
        "zenskill.unit.minute": "Minuten",
        "zenskill.readout.delegation": "Agent übernimmt",
        "zenskill.readout.delegationHint": "{n} von {total} vom Agenten übernommen",
        "zenskill.readout.energyRecovering": "Erholt sich +{n} Punkte",
        "zenskill.profile.understandingError": "Basierend auf {n} Stichproben · Fehlerbereich ±{e}",
    },
    "es": {
        "zenskill.collaboration.statsEmpty": "Aún no hay estadísticas de habilidades — instala otra habilidad para verlas",
        "zenskill.collaboration.transferEmpty": "Aún no hay patrones transferibles — aparecen cuando usas una habilidad durante tiempo",
        "zenskill.cultivation.card.thought.empty": "Ahora mismo no se puede leer la biblioteca de citas — vuelve más tarde",
        "zenskill.cultivation.growth.levelsEmpty": "Aún no hay niveles de habilidad — registra un uso en el área de Habilidades",
        "zenskill.gtd.actions.empty": "Sin acciones pendientes — elige una del buzón",
        "zenskill.gtd.calendar.dayActionsEmpty": "Nada vence este día — añade un evento para hoy",
        "zenskill.gtd.calendar.dayEmpty": "Sin eventos este día — añade uno",
        "zenskill.gtd.calendar.empty": "Hoy no hay eventos — añade uno",
        "zenskill.gtd.calendar.suggestEmpty": "Sin sugerencias disponibles — anota qué hay que hacer esta semana",
        "zenskill.gtd.inbox.empty": "Nada pendiente — captura una idea",
        "zenskill.gtd.incubating.empty": "Nada en incubación — captura primero una idea",
        "zenskill.gtd.projects.actionsEmpty": "Sin acciones abiertas — elige una de un proyecto",
        "zenskill.gtd.projects.empty": "No hay proyectos activos — crea uno",
        "zenskill.insights.empty": "Ningún insight coincide con los filtros — prueba otro filtro",
        "zenskill.market.empty": "Sin resultados — busca con otra palabra clave",
        "zenskill.memory.empty": "Aún no hay recuerdos — conversa un poco para que el agente te conozca",
        "zenskill.panel.goals.empty": "Sin objetivos — define uno",
        "zenskill.panel.memory.empty": "No hay recuerdos guardados — conversa un poco para que el agente te conozca",
        "zenskill.profile.goals.empty": "Sin metas activas — define una",
        "zenskill.profile.habitsEmpty": "Aún no hay datos de hábitos — añade un hábito en Ajustes · ZenSkill",
        "zenskill.skillGraph.empty": "Aún no hay datos de habilidades — instala una habilidad",
        "zenskill.skillGraph.emptyDomain": "Sin habilidades en este dominio — instala una",
        "zenskill.toast.captured": "Capturado",
        "zenskill.collaboration.gap": "Brecha:",
        "zenskill.collaboration.overview": "Resumen del Ecosistema",
        "zenskill.collaboration.transfer": "Patrones Transferibles",
        "zenskill.collaboration.insights": "Perspectivas entre Habilidades",
        "zenskill.session.empty": "Aún no hay sesión — crea una",
        "zenskill.state.loading": "Cargando",
        "zenskill.state.error.title": "Este bloque no se puede leer ahora",
        "zenskill.state.error.retry": "Reintentar",
        "zenskill.state.noAccess.title": "Este espacio de trabajo no tiene fuente de datos de ZenSkill",
        "zenskill.state.noAccess.hint": "Añade una fuente de datos de ZenSkill a este espacio de trabajo y aquí aparecerán los datos de crecimiento y proceso",
        "zenskill.readout.loop": "Ciclo",
        "zenskill.readout.loopCount": "{n} en marcha",
        "zenskill.readout.energy": "Energía",
        "zenskill.readout.attention": "Atención",
        "zenskill.readout.atMost": "como máximo",
        "zenskill.readout.attentionUpperHint": "El uso de foco reciente no se puede leer ahora — este valor es un máximo",
        "zenskill.unit.point": "puntos",
        "zenskill.unit.minute": "minutos",
        "zenskill.readout.delegation": "El agente asume",
        "zenskill.readout.delegationHint": "{n} de {total} asumidos por el agente",
        "zenskill.readout.energyRecovering": "recuperando +{n} puntos",
        "zenskill.profile.understandingError": "Basado en {n} muestras · rango de error ±{e}",
    },
    "hu": {
        "zenskill.collaboration.statsEmpty": "Még nincsenek készségstatisztikák — telepítsz még egy készséget, hogy lásd",
        "zenskill.collaboration.transferEmpty": "Még nincsenek átvehető minták — akkor jelennek meg, ha egy készséget hosszabb ideig használsz",
        "zenskill.cultivation.card.thought.empty": "Az idézetkönyvtár most nem olvasható — nézz vissza később",
        "zenskill.cultivation.growth.levelsEmpty": "Még nincsenek készségszintek — jegyezz egy használatot a Készségek területen",
        "zenskill.gtd.actions.empty": "Nincsenek feldolgozandó műveletek — válassz egyet a beérkezőkből",
        "zenskill.gtd.calendar.dayActionsEmpty": "Ezen a napon nem esedékes — adj hozzá egy eseményt mára",
        "zenskill.gtd.calendar.dayEmpty": "Ezen a napon nincs esemény — adj hozzá egyet",
        "zenskill.gtd.calendar.empty": "Ma nincsenek események — adj hozzá egyet",
        "zenskill.gtd.calendar.suggestEmpty": "Nincsenek javaslatok — írd le, mit kell elvégezni ezen a héten",
        "zenskill.gtd.inbox.empty": "Nincs feldolgozandó — jegyezz le egy ötletet",
        "zenskill.gtd.incubating.empty": "Nincs inkubálódó elem — előbb jegyezz le egy ötletet",
        "zenskill.gtd.projects.actionsEmpty": "Nincsenek nyitott teendők — válassz egyet egy projektből",
        "zenskill.gtd.projects.empty": "Nincsenek aktív projektek — hozz létre egyet",
        "zenskill.insights.empty": "Egyik meglátás sem felel meg a szűrőknek — próbálj másik szűrőt",
        "zenskill.market.empty": "Nincsenek találatok — keresd más kulcsszóval",
        "zenskill.memory.empty": "Még nincsenek emlékek — beszélj néhány szót, hogy az ügynök megismerjen",
        "zenskill.panel.goals.empty": "Nincsenek célok — állíts be egyet",
        "zenskill.panel.memory.empty": "Nincsenek tárolt emlékek — beszélj néhány szót, hogy az ügynök megismerjen",
        "zenskill.profile.goals.empty": "Nincsenek aktív célok — állíts be egyet",
        "zenskill.profile.habitsEmpty": "Még nincsenek szokásadatok — adj hozzá egy szokást a Beállítások · ZenSkill alatt",
        "zenskill.skillGraph.empty": "Még nincsenek készségadatok — telepíts egy készséget",
        "zenskill.skillGraph.emptyDomain": "Nincs készség ebben a tartományban — telepíts egyet",
        "zenskill.toast.captured": "Rögzítve",
        "zenskill.collaboration.gap": "Res:",
        "zenskill.collaboration.overview": "Okoszisztima attekintese",
        "zenskill.collaboration.transfer": "Atadhato Mintak",
        "zenskill.collaboration.insights": "Keszsegkozi Betekintesek",
        "zenskill.session.empty": "Még nincs munkamenet — hozz létre egyet",
        "zenskill.state.loading": "Betöltés",
        "zenskill.state.error.title": "Ez a blokk most nem olvasható",
        "zenskill.state.error.retry": "Újra",
        "zenskill.state.noAccess.title": "Ennek a munkaterületnek nincs ZenSkill adatforrása",
        "zenskill.state.noAccess.hint": "Adj meg egy ZenSkill adatforrást ehhez a munkaterülethez, és itt megjelennek a növekedés és folyamat adatai",
        "zenskill.readout.loop": "Kör",
        "zenskill.readout.loopCount": "{n} fut",
        "zenskill.readout.energy": "Energia",
        "zenskill.readout.attention": "Figyelem",
        "zenskill.readout.atMost": "legfeljebb",
        "zenskill.readout.attentionUpperHint": "A legutóbbi fókuszhasználat most nem olvasható — ez az érték felső korlát",
        "zenskill.unit.point": "pont",
        "zenskill.unit.minute": "perc",
        "zenskill.readout.delegation": "Az ügynök átvállal",
        "zenskill.readout.delegationHint": "{n} / {total} átvállalva az ügynök által",
        "zenskill.readout.energyRecovering": "visszaszerzés +{n} pont",
        "zenskill.profile.understandingError": "{n} minta alapján · hibatartomány ±{e}",
    },
    "ja": {
        "zenskill.collaboration.statsEmpty": "スキル統計はまだありません — もう一つスキルを入れると表示されます",
        "zenskill.collaboration.transferEmpty": "転移可能なパターンはまだありません — 同じスキルを長く使うと現れます",
        "zenskill.cultivation.card.thought.empty": "引用集は一時的に読み取れません — あとでまた来看看てください",
        "zenskill.cultivation.growth.levelsEmpty": "スキル等級はまだありません — 「スキル」領域で一度使う記録を付けてください",
        "zenskill.gtd.actions.empty": "保留中のアクションはありません — 「受信トレイ」から一つ選びましょう",
        "zenskill.gtd.calendar.dayActionsEmpty": "この日に期限のアクションはありません — 今日の予定を一つ追加してみましょう",
        "zenskill.gtd.calendar.dayEmpty": "この日の予定はありません — 一つ追加してみましょう",
        "zenskill.gtd.calendar.empty": "今日のイベントはありません — 一つ追加してみましょう",
        "zenskill.gtd.calendar.suggestEmpty": "利用可能な提案はありません — 今週やりたいことを書いてみましょう",
        "zenskill.gtd.inbox.empty": "保留中のアイテムはありません — アイデアを記録してみましょう",
        "zenskill.gtd.incubating.empty": "孵化中の項目はありません — まずアイデアを記録してみましょう",
        "zenskill.gtd.projects.actionsEmpty": "進行中のアクションはありません — プロジェクトから一つ選びましょう",
        "zenskill.gtd.projects.empty": "進行中のプロジェクトはありません — 一つ作成してみましょう",
        "zenskill.insights.empty": "フィルターに一致するインサイトはありません — 別の条件に変えてみてください",
        "zenskill.market.empty": "結果はまだありません — 別のキーワードで検索してみましょう",
        "zenskill.memory.empty": "記憶はまだありません — 少し話すとエージェントがあなたを覚えます",
        "zenskill.panel.goals.empty": "目標はありません — 一つ立ててみましょう",
        "zenskill.panel.memory.empty": "保存されたメモリはありません — 少し話すとエージェントがあなたを覚えます",
        "zenskill.profile.goals.empty": "実行中の目標はありません — 一つ立ててみましょう",
        "zenskill.profile.habitsEmpty": "習慣データはまだありません — 「設定 · ZenSkill」で習慣を追加しましょう",
        "zenskill.skillGraph.empty": "スキルデータはまだありません — スキルを一つ入れてみましょう",
        "zenskill.skillGraph.emptyDomain": "このドメインにスキルはありません — 一つ入れてみましょう",
        "zenskill.toast.captured": "キャプチャ済み",
        "zenskill.collaboration.gap": "差分:",
        "zenskill.collaboration.overview": "エコシステム概要",
        "zenskill.collaboration.transfer": "転移可能なパターン",
        "zenskill.collaboration.insights": "スキル横断インサイト",
        "zenskill.session.empty": "セッションはまだありません — 作成してみましょう",
        "zenskill.state.loading": "読み込み中",
        "zenskill.state.error.title": "このブロックは一時的に読み取れません",
        "zenskill.state.error.retry": "再試行",
        "zenskill.state.noAccess.title": "このワークスペースには ZenSkill データソースがありません",
        "zenskill.state.noAccess.hint": "このワークスペースに ZenSkill データソースを追加すると、成長と過程の読み取りがここに表示されます",
        "zenskill.readout.loop": "ループ",
        "zenskill.readout.loopCount": "{n} 件進行中",
        "zenskill.readout.energy": "エネルギー",
        "zenskill.readout.attention": "集中力",
        "zenskill.readout.atMost": "最大",
        "zenskill.readout.attentionUpperHint": "直近の集中使用量は一時的に読み取れません — この値は上限です",
        "zenskill.unit.point": "ポイント",
        "zenskill.unit.minute": "分",
        "zenskill.readout.delegation": "エージェントが担当",
        "zenskill.readout.delegationHint": "{total} 件中 {n} 件をエージェントが担当",
        "zenskill.readout.energyRecovering": "回復中 +{n} ポイント",
        "zenskill.profile.understandingError": "{n} サンプルに基づく · 誤差範囲 ±{e}",
    },
    "pl": {
        "zenskill.collaboration.statsEmpty": "Brak statystyk umiejętności — zainstaluj jeszcze jedną, żeby je zobaczyć",
        "zenskill.collaboration.transferEmpty": "Brak wzorców do przeniesienia — pojawiają się, gdy długo korzystasz z umiejętności",
        "zenskill.cultivation.card.thought.empty": "Biblioteka cytatów jest teraz nieczytelna — zajrzyj później",
        "zenskill.cultivation.growth.levelsEmpty": "Brak poziomów umiejętności — zarejestruj użycie w obszarze Umiejętności",
        "zenskill.gtd.actions.empty": "Brak oczekujących akcji — wybierz jedną ze skrzynki",
        "zenskill.gtd.calendar.dayActionsEmpty": "Brak zadań z terminem na ten dzień — dodaj wydarzenie na dziś",
        "zenskill.gtd.calendar.dayEmpty": "Brak wydarzeń tego dnia — dodaj jedno",
        "zenskill.gtd.calendar.empty": "Brak wydarzeń na dziś — dodaj jedno",
        "zenskill.gtd.calendar.suggestEmpty": "Brak dostępnych propozycji — zapisz, co masz zrobić w tym tygodniu",
        "zenskill.gtd.inbox.empty": "Nic do przetworzenia — zapisz jakiś pomysł",
        "zenskill.gtd.incubating.empty": "Nic w inkubacji — najpierw zapisz jakiś pomysł",
        "zenskill.gtd.projects.actionsEmpty": "Brak otwartych zadań — wybierz jedno z projektu",
        "zenskill.gtd.projects.empty": "Brak aktywnych projektów — utwórz jeden",
        "zenskill.insights.empty": "Brak wglądów pasujących do filtrów — spróbuj innego filtra",
        "zenskill.market.empty": "Brak wyników — wyszukaj innym słowem kluczowym",
        "zenskill.memory.empty": "Brak zapisanych wspomnień — porozmawiaj chwilę, żeby agent cię poznał",
        "zenskill.panel.goals.empty": "Brak celów — ustaw jeden",
        "zenskill.panel.memory.empty": "Brak zapisanych wspomnień — porozmawiaj chwilę, żeby agent cię poznał",
        "zenskill.profile.goals.empty": "Brak aktywnych celów — ustaw jeden",
        "zenskill.profile.habitsEmpty": "Brak danych nawyków — dodaj nawyk w Ustawieniach · ZenSkill",
        "zenskill.skillGraph.empty": "Brak danych umiejętności — zainstaluj umiejętność",
        "zenskill.skillGraph.emptyDomain": "Brak umiejętności w tej domenie — zainstaluj jedną",
        "zenskill.toast.captured": "Przechwycono",
        "zenskill.collaboration.gap": "Roznica:",
        "zenskill.collaboration.overview": "Przeglad Ekosystemu",
        "zenskill.collaboration.transfer": "Wzorce Przenoszenia",
        "zenskill.collaboration.insights": "Spojrzenia Miedzy Umiejetnosciami",
        "zenskill.session.empty": "Brak sesji — utwórz jedną",
        "zenskill.state.loading": "Ładowanie",
        "zenskill.state.error.title": "Tego bloku nie da się teraz odczytać",
        "zenskill.state.error.retry": "Spróbuj ponownie",
        "zenskill.state.noAccess.title": "Ten obszar roboczy nie ma źródła danych ZenSkill",
        "zenskill.state.noAccess.hint": "Dodaj źródło danych ZenSkill do tego obszaru roboczego, a pojawią się tutaj odczyty wzrostu i procesu",
        "zenskill.readout.loop": "Pętla",
        "zenskill.readout.loopCount": "{n} w toku",
        "zenskill.readout.energy": "Energia",
        "zenskill.readout.attention": "Uwaga",
        "zenskill.readout.atMost": "najwyżej",
        "zenskill.readout.attentionUpperHint": "Najnowsze zużycie skupienia jest teraz nieczytelne — ta wartość to górna granica",
        "zenskill.unit.point": "punktów",
        "zenskill.unit.minute": "minut",
        "zenskill.readout.delegation": "Agent przejmuje",
        "zenskill.readout.delegationHint": "{n} z {total} przejętych przez agenta",
        "zenskill.readout.energyRecovering": "odzyskuje +{n} pkt",
        "zenskill.profile.understandingError": "Na podstawie {n} próbek · zakres błędu ±{e}",
    },
}


# ── 退役的 key（通用五态文案迁到 `zenskill.state.*` 后，原 `cultivation.*` 那 5 条**必须删掉**）──
# ★ 为什么必须删：locale 里留着就成了**孤儿 key**（没有真相源登记、也没有任何页面引用）
#   ⇒ 门禁 C-11 的「漏登记」会判红，而且它们是「同一概念的第二个名字」⇒ 违反不另造同义词。
REMOVED_KEYS = (
    "zenskill.cultivation.loading",
    "zenskill.cultivation.error.title",
    "zenskill.cultivation.error.retry",
    "zenskill.cultivation.noDataSource.title",
    "zenskill.cultivation.noDataSource.hint",
)


def dump(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    check = "--check" in sys.argv
    expected = set(T["zh-Hans"])
    bad = 0
    for loc, table in T.items():
        if set(table) != expected:
            print(f"[FAIL] {loc}: key 集合与 zh-Hans 不一致")
            bad += 1
        path = LOCALES_DIR / f"{loc}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        missing = expected - set(data)
        if missing:
            # ★ 写模式下「缺 key」是**正常**的（这次就是新增 key）；
            #   只有 --check 模式才判红（那时文件本该已经写好 ⇒ 缺 = 没写成功）。
            if check:
                print(f"[FAIL] {loc}: 缺 {len(missing)} 个 key")
                bad += 1
            else:
                print(f"[新增] {loc}: 新增 {len(missing)} 个 key（{', '.join(sorted(missing))}）")
        merged = {**data, **table}
        for k in REMOVED_KEYS:
            merged.pop(k, None)
        if check:
            if path.read_text(encoding="utf-8") != dump(merged):
                print(f"[FAIL] {loc}: 文件内容与预期不一致（--check 判红）")
                bad += 1
            else:
                print(f"[OK] {loc}: {len(table)} 条五态文案与预期一致")
        else:
            path.write_text(dump(merged), encoding="utf-8")
            print(f"[OK] {loc}: 写入 {len(table)} 条五态文案（共 {len(merged)}）")
    # 全 locale key 集合一致性
    keysets = {loc: set(json.loads((LOCALES_DIR / f"{loc}.json").read_text(encoding="utf-8"))) for loc in T}
    base = keysets["zh-Hans"]
    for loc, ks in keysets.items():
        if ks != base:
            print(f"[FAIL] {loc}: 与 zh-Hans 的 key 集合不一致（差 {len(ks ^ base)} 项）")
            bad += 1
    if bad:
        print(f"\n[FAIL] {bad} 项不通过")
        return 1
    print("\n✅ 五态文案 7 locale 一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
