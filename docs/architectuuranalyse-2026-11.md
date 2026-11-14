# Architectuuranalyse snakeboot 0.13.2

Datum: 14 november 2026. Basis: de broncode op `main` (9cfb0ce), de README, de import-contracten, de GitHub-issues
en eigen metingen op Windows 11 met Python 3.13. Wat over de buitenwereld gaat (Spring AI, MCP, upstream-projecten)
komt uit mijn kennis tot midden 2026 en is niet opnieuw opgezocht.

Sindsdien opgelost: bevinding 1 van sectie 1.1 ("wireup is publieke API") en punt 1 van de roadmap (5.1) zijn
uitgevoerd in 0.14.0 (`snakeboot.stereotype`: `@component`, `@service`, `@repository`, `@bean`, `Qualifier`). De rest
van dit document beschrijft 0.13.2 en is niet bijgewerkt.

## 0. De feiten waarop dit steunt

| Gegeven | Waarde |
|---|---|
| Broncode | 12.400 regels in 25 packages |
| Tests | 13.000 regels; 888 geslaagd, 11 overgeslagen (PostgreSQL en RabbitMQ niet gestart), 43 s |
| Geschiedenis | 48 commits sinds 22 oktober 2026, 1 auteur, 13 minor-releases in 3 weken |
| Gebruik | 0 sterren, 0 forks; bekende toepassingen: Subsidar en de tutorial-applicaties |
| Verplichte afhankelijkheid | alleen `wireup` |
| Import van de frameworks (warm) | ca. 1,2 s, 1.012 modules |
| snakeboot daarbovenop | ca. 0,1 s |
| Eerste start van een kleine applicatie | ca. 0,3 s; een tweede start in hetzelfde proces 17 ms |
| Eerste request | ca. 0,2 s |

De code is opvallend gedisciplineerd: mypy strict, 35 `noqa`/`type: ignore` in totaal, kleine bestanden (het
grootste productiebestand telt 408 regels), en de poort naar de persistentie (`RepositoryOperations`) heeft zeven
methodes. De kritiek hieronder gaat dus niet over vakmanschap, maar over strategie.

## 1. Architectuur, onderhoudbaarheid en haalbaarheid

### 1.1 Houdt de abstractie stand?

Grotendeels, omdat ze smal is. De FastAPI-binding is ongeveer 700 regels en raakt alleen stabiele, publieke API
(`add_api_route`, `Security`, `add_exception_handler`, een samengestelde `__signature__`). De SQLAlchemy-binding
vertaalt een kleine querytaal naar `select()`. Dat is geen "ORM boven een ORM", en daarom is het houdbaar.

Maar de centrale belofte, "een applicatie importeert alleen snakeboot", klopt vandaag niet helemaal:

1. **wireup is publieke API.** De README gebruikt `@injectable` (regels 286 en 513), en 21 testbestanden doen
   `from wireup import injectable`. Geen enkel snakeboot-package exporteert die naam. De import-contracten en
   `tests/test_without_a_web_framework.py` controleren snakeboot zelf en de web-, data- en cacheframeworks, niet
   wat een applicatie van wireup ziet. wireup is bovendien het werk van één onderhouder, en het is de enige
   verplichte afhankelijkheid. `ApplicationContext._registrable_part_of` werkt al om een eigenschap van wireup heen
   (het registreert ook wat een module importeerde), en wireup importeert zelf FastAPI zodra dat geïnstalleerd is.
2. **Pydantic is publieke API.** Een request-body, een RabbitMQ-bericht en elke `Section` zijn Pydantic-modellen.
   Dat is verdedigbaar (Jackson is ook de facto deel van Spring Boot), maar zeg het dan: "een applicatie spreekt
   snakeboot en Pydantic".
3. **De vorm van de antwoorden is die van FastAPI.** Het OpenAPI-document, de 422 zonder advice en de 401
   `{"detail": "Unauthorized"}` komen van FastAPI. Een andere webbinding moet die byte voor byte nabootsen.

De grootste lekrisico's, in volgorde van ernst:

| Lek | Waarom het telt |
|---|---|
| **Alleen synchroon** | `@transactional` weigert `async def`; elke endpoint draait op Starlettes threadpool (standaard 40 threads). Dat is geen bug maar een keuze, alleen staat ze nergens als keuze beschreven. Voor wie LLM-aanroepen van 30 seconden doet, is dit het plafond. |
| **Geen instelbare connectiepool** | `create_engine` krijgt geen `pool_size`: SQLAlchemy's standaard is 5 + 10 overloop, tegenover 40 requestthreads, 8 taakthreads, de scheduler en één thread per listener. Onder last wachten threads op een connectie en volgt een time-out. |
| **SQL-dialect** | `@query` en de migraties zijn rauwe SQL. De tests draaien standaard op SQLite, productie op PostgreSQL. Het project lost dat netjes op met `PostgreSQLContainer`, maar de abstractie "snakeboot kiest de database" bestaat dus niet: de applicatie kiest PostgreSQL. |
| **JPA-semantiek, stuk voor stuk** | De sessie "houdt wat ze las", `Version()`, en nu issues #15 (`OPTIMISTIC_FORCE_INCREMENT`) en #16 (`clearAutomatically`). Dit is het begin van Hibernate nabouwen, één issue per keer. De README zegt "zoals Spring Data JDBC" (geen relaties); de implementatie leunt op een JPA-achtige identity map. Kies. |
| **Geen dynamische queries** | Afgeleide namen en statische `@query`. Een zoekscherm met zes optionele filters heeft geen nette oplossing en geen nooduitgang naar de sessie. |
| **Eén applicatie, één database per proces** | `TransactionManagerRegistry` is procesglobaal. Prima voor nu, maar het is een grens. |
| **Privé-API van SQLAlchemy** | `OneThreadAtATimePool` overschrijft `_do_get` en `_do_return_conn`. Alleen in tests, dus een klein risico, maar het breekt zonder waarschuwing. |

**De verwisselbaarheid is een hypothese.** Web, data en messaging hebben elk precies één binding. Een abstractie met
één implementatie is niet bewezen; ze is ontworpen rond wat die ene implementatie kan. De eigen regel "een feature
hoort erbij wanneer twee applicaties ze nodig hebben" geldt ook hier: claim verwisselbaarheid pas wanneer een tweede
binding bestaat, of formuleer de belofte als wat ze werkelijk oplevert: *een applicatie is niet aan FastAPI's
API gebonden wanneer FastAPI verandert*. Dat is al veel waard, en het is waar.

RabbitMQ is trouwens geen binding: `@rabbit_listener` noemt de broker in de code van de applicatie, zoals Spring AMQP.
Kafka zou een nieuw feature-package zijn, geen wissel.

### 1.2 Onderhoudslast

De adapters zijn niet het probleem; de breedte is het. 25 packages, één persoon, drie weken oud.

* **Geen bovengrenzen.** `fastapi>=0.162.2`, `sqlalchemy>=2.1.8`, `wireup>=2.13.1`. FastAPI is 0.x en breekt in
  minors. De CI draait met `--locked`, dus ze ziet een brekende upstream-release niet; een gebruiker die vandaag
  installeert wel.
* **Tempo.** Dertien minor-releases in drie weken, die elk de API mogen breken. Dat is goed om te ontdekken, maar
  niemand kan daarop bouwen. Het oppervlak groeit sneller dan productie het kan bewijzen.
* **Bus factor 1**, twee keer: snakeboot zelf en wireup.
* **Python 3.14** staat in de CI, dus de uitgestelde annotaties (PEP 649/749) zijn afgedekt. Dat is het punt waar
  een framework dat annotaties leest het eerst breekt; goed dat het er staat.
* **pika** is synchroon en beweegt traag: één thread en één connectie per listener. Voldoende, maar het schaalt niet
  naar honderden wachtrijen.

### 1.3 Prestaties en opstartkost

De metingen zeggen het: snakeboot zelf kost ongeveer een tiende seconde. De scan, de reflectie en wireup zijn geen
knelpunt. Wat telt:

* **Koude start** wordt bepaald door FastAPI, Pydantic, SQLAlchemy en Alembic: 1,2 tot 2,2 s aan imports. Voor
  containers irrelevant, voor AWS Lambda of scale-to-zero merkbaar. `snakeboot.boot` laadt wel al lui (een commando
  zonder server laadt geen FastAPI), wat de juiste reflex is.
* **Fail at start-up heeft een prijs**: alle listeners worden gebouwd, alle RabbitMQ-declaraties gedaan. Bij een
  grote applicatie met een trage broker verlengt dat de readiness.
* **Het echte plafond is gelijktijdigheid**, niet latentie: 40 threads per proces, en de GIL voor CPU-werk.
* **`ServerSentEvents.watching` pollt.** Elke kijker leest elke `every` de database. 1.000 kijkers op 500 ms zijn
  2.000 queries per seconde. Voor een spel prima, voor een dashboard niet.
* **De scheduler heeft één thread**: een taak van tien minuten houdt alle andere tegen.
* **De taakexecutor** heeft 8 threads en een onbegrensde wachtrij: geen tegendruk.
* **Elke uvicorn-worker** heeft zijn eigen scheduler, listeners en metrics. De README zegt dat eerlijk.

Een strategische meevaller: het synchrone threadmodel is precies wat van free-threaded Python (officieel ondersteund
vanaf 3.14) profiteert, zoals Spring MVC van virtual threads. "Synchroon, zoals Spring MVC" is een verdedigbare
positie, mits ze uitgesproken en instelbaar is.

## 2. De tijdgeest en het eerlijke oordeel

**Het probleem is echt, het publiek is klein.** Teams die uit de JVM komen missen in Python precies dit: één plaats
waar de applicatie start, getypeerde configuratie die bij een typfout stopt, transactiegrenzen, en vooral tests van
de hele applicatie zonder `conftest.py`-archeologie. FastAPI lost routing op en laat de rest aan elk team over.

**Het "on-Pythonische" verwijt is het zwakste bezwaar.** Decorators, dataclasses en `Protocol` zijn idiomatisch
Python; pytest is zelf pure magie. Wat wél schuurt:

* queries in methodenamen (`find_by_status_and_join_deadline_less_than_equal`): geen IDE helpt, alleen de start;
* een README die elk begrip uitlegt als "zoals `@MockitoBean`": onleesbaar voor wie Spring niet kent;
* alleen synchroon, in een ecosysteem dat async als norm ziet. Dit is het bezwaar dat adoptie werkelijk kost.

**De echte concurrenten** zijn niet de puristen maar: Django (het bestaande "batterijen inbegrepen"), Litestar
(controllers als klassen, DI en een testclient ingebouwd), en "FastAPI plus een cookiecutter en dishka of
dependency-injector". Tegenover elk daarvan is het onderscheid van snakeboot: afgedwongen hexagonale grenzen,
fail-at-start-up, de outbox, en het testverhaal.

**Ideale doelgroep**, in volgorde:

1. **Onderwijs.** Hexagonale architectuur en DDD aanleren aan studenten die Spring Boot kennen, met de
   tweelingapplicatie als bewijs. Hier is snakeboot vandaag al het beste gereedschap dat bestaat.
2. **Gemengde JVM/Python-organisaties** waar AI- en dataservices in Python moeten, maar door Java-gevormde teams
   worden onderhouden.
3. **Interne platformteams** die één manier van werken willen opleggen.

Niet: Python-native start-ups, async-zware systemen, Django-shops.

**Het plafond.** Als open source: een niche. De naamgeving naar Spring is tegelijk het verkoopargument en de grens.
Realistisch zijn enkele tientallen echte gebruikers, bij een sterk verhaal honderden; een brede Python-standaard
wordt het niet. Commercieel is er geen product, wel waarde als intern platform, als lesmateriaal en als drager voor
advieswerk. Dat is geen falen: het is een eerlijke maat. De vraag is niet "hoe wordt dit groot" maar "voor wie is
dit onmisbaar".

## 3. AI-agents en MCP

### 3.1 Als backend voor agents

Wat al past, en beter dan in de meeste Python-stacks:

| Behoefte van een agent | Wat snakeboot heeft |
|---|---|
| Een tool die half slaagt mag niets achterlaten | `@transactional` rond de use case |
| Berichten tussen agents die niet verloren gaan | de outbox: minstens één keer, met herhaling en een wachtrij voor wat blijft falen |
| Twee agents die dezelfde toestand wijzigen | `Version()` en `OptimisticLockingFailureError` |
| Eén agentlus per cluster | `@scheduler_lock` |
| Wie deed dit | `Principal`, `CreatedBy`, `LastModifiedBy` |
| Eén spoor door alle stappen | `traceparent` in requests, berichten, listeners en logs |
| Deterministische tests zonder LLM | de LLM is een poort, dus een `MockComponent` |

Wat ontbreekt:

* **Lange I/O.** Een LLM-aanroep duurt 10 tot 120 s en houdt een thread vast. Erger: binnen `@transactional` houdt
  hij ook een databaseconnectie vast. Er is een regel nodig ("geen uitgaande aanroep in een transactie") en liefst
  een waarschuwing wanneer het toch gebeurt.
* **Idempotentie.** Agents herhalen aanroepen. Een sleutel per aanroep, bewaard in een tabel van snakeboot zoals de
  scheduler-lock, is klein en waardevol.
* **Stromen van tokens.** `watching` pollt; een stroom uit een gewone (synchrone) generator ontbreekt.
* **Een uitgaande HTTP-client** met time-outs en herhaling (issue #5): een agent is vooral uitgaand verkeer.
* **Langlopende taken** met een status die een client kan opvragen.

### 3.2 MCP als eerste-klas inkomende adapter

Ja, en het past ongewoon goed, omdat een MCP-tool precies is wat een REST-endpoint is: een inkomende adapter op een
use case. Het ontwerp volgt het bestaande patroon:

```python
@mcp_server("/mcp")
class FundingTools:
    def __init__(self, calls: OpenCallsUseCase) -> None:
        self._calls = calls

    @mcp_tool(read_only=True)
    @roles_allowed("researcher")
    def list_open_calls(self, programme: str, page: PageRequest, caller: Principal) -> list[CallDTO]:
        """Lists the funding calls that are open, newest first."""
        return self._calls.execute(programme, page, researcher=caller.name)
```

* `snakeboot.mcp`: alleen markeringen en de scan, zoals `snakeboot.rest` (standaardbibliotheek en wireup).
* Een binding op de officiële Python-SDK, die de server als ASGI naast `/api` zet (streamable HTTP) en als commando
  `python -m myapp mcp` over stdio. De SDK en de specificatie bewegen snel: houd de binding dun.
* Hergebruik: de signatuur wordt het JSON-schema, `Principal` en `@roles_allowed` gelden per tool, een advice wordt
  een toolfout, elke aanroep krijgt een span en een meter, `JwtBearerAuthentication` is de OAuth-resourceserver die
  MCP's autorisatie verwacht (plus het metadata-document dat de specificatie vraagt).
* Fail at start-up: een tool zonder docstring, twee tools met één naam, een parameter zonder schema, een lijst
  zonder `PageRequest` stoppen de start. Een beschrijving is voor een LLM geen documentatie maar de interface.
* **Tests**: `@mcp_test` als slice en `Autowired[McpClient]` in hetzelfde proces. Dit is waar snakeboot zich
  onderscheidt: MCP-servers worden vandaag nauwelijks getest.

**Stel geen repositories bloot.** Een repository als tool omzeilt de invarianten van het domein en de autorisatie,
en CRUD-tools zijn slecht ontwerp voor een LLM (te veel, te fijn). Stel use cases bloot. Veiligheid komt van:
alleen-lezen versus wijzigend als verplichte keuze, rollen per tool, een transactie per aanroep, verplichte
paginering, en de agent als `Principal` in de audit.

De regel van twee applicaties: Subsidar heeft al een MCP-server. Er is een tweede nodig vóór dit in snakeboot hoort;
de tutorial-applicatie is de voor de hand liggende.

### 3.3 Wat van Spring AI overnemen

| Concept | Oordeel |
|---|---|
| MCP-serverstarter met annotaties | **Ja**, zie hierboven. |
| Tooldefinities uit methodes | **Ja, gratis erbij**: dezelfde `@mcp_tool` levert naam, beschrijving en schema voor de eigen agent in het proces. |
| VectorStore | **Klein**: `Vector` bestaat; een afgeleide zoekmethode op gelijkenis volstaat. Geen eigen store-abstractie. |
| ChatClient, modelabstractie | **Nee.** De SDK's en bibliotheken daarvoor veranderen per week; dit is een onderhoudsmijn, en de LLM is in een hexagonale applicatie al een poort. |
| Advisors | **Nee**: zonder ChatClient is er niets om te omringen. |
| Gestructureerde uitvoer | **Nee**: Pydantic en de SDK's doen het al. |
| Evaluatieharnas | **Later, hooguit dun**: de teststijl is de sterkte, maar evaluatie van modellen is domein van de applicatie. |
| Chatgeheugen | **Nee**: dat is een repository. |

## 4. Inspiratie uit Spring

| Onderwerp | Oordeel | Toelichting |
|---|---|---|
| `@retryable` | **Ja, klein** | Alleen standaardbibliotheek. Spring Framework 7 nam het zelf in de kern op. Let op de volgorde: de herhaling omsluit de transactie. |
| Circuit breaker | **Alleen in de HTTP-client** | Los ervan is het een oplossing zonder probleem. |
| Rate limiting | **Nee** | Hoort in de gateway of de ingress. |
| Achtergrondtaken | **Bestaat al voor 80 %** | Een `@application_module_listener` met de outbox *is* een duurzame taak met herhaling. Documenteer dat, en voeg toe wat ontbreekt: mislukte publicaties tonen en opnieuw aanbieden (een commando en een actuator-endpoint), en opruimen. Geen Celery nabouwen. |
| Cron voor `@scheduled` | **Ja** | "Elke nacht om 2 uur" is de eerste vraag van elk productieteam; `fixed_rate` kan dat niet. De README sluit cron uit; dat is de verkeerde besparing. |
| `@externalized` (Spring Modulith) | **Ja** | Een event uit de outbox naar RabbitMQ, atomair met de transactie. Het verbindt twee dingen die er al zijn. |
| `ApplicationModules.verify()` (Spring Modulith) | **Ja, hoog** | Controleer dat bounded contexts elkaar alleen via hun publieke deel en events raken, en genereer er documentatie uit. Het past bij de kern van het project en `declared_classes` is het begin. |
| HTTP-interfaceclient | **Ja** | Een `Protocol` met `@http_exchange`, door snakeboot geïmplementeerd zoals een repository, met een nepserver voor tests (#5). |
| `@pre_authorize` met expressies | **Nee** | Geen SpEL. Laat `@roles_allowed` wel op elke componentmethode werken, want MCP-tools en listeners zijn ook ingangen. "Is dit mijn veiling" is domeinlogica. |
| OpenTelemetry | **Ja, als binding** | Vandaag bestaat het spoor alleen in logs; spans gaan nergens heen. Een optionele OTLP-binding achter `TraceContext` en `MeterRegistry`. Ondernemingen eisen dit. |
| `@cacheable` | Laag | Handig, maar het is AOP via de achterdeur. |
| Geheimen uit bestanden | **Ja, klein** | Kubernetes en Docker leveren geheimen als bestanden; nu kan alleen een omgevingsvariabele. |
| Spring Batch, Spring Cloud Config/Gateway | **Nee** | Dat is Spring, niet de basis van Spring Boot. |

## 5. Roadmap

### 5.1 Laaghangend fruit

1. **Exporteer `injectable` uit snakeboot** (of noem het `@component`), en laat een test bewijzen dat de
   voorbeeldapplicaties alleen snakeboot en Pydantic importeren. Dat maakt de hoofdbelofte waar.
2. **Een wekelijkse CI-run tegen de nieuwste upstream-versies** (`uv sync --upgrade`), en bovengrenzen op FastAPI
   en wireup.
3. **`[database] pool_size`** en de grootte van de threadpool in `[server]`; stop de start wanneer ze niet bij
   elkaar passen.
4. **Een startpunt**: `uvx snakeboot new myapp` of een template-repository. start.spring.io is dé ergonomie van
   Spring Boot, en ze ontbreekt.
5. **Een quickstart van vijf minuten zonder Spring-woordenschat**, en de README (803 regels) opsplitsen in een
   documentatiesite. De tweelingtutorial is het beste materiaal dat er is: publiceer ze als de documentatie.
6. **Cron** en **geheimen uit bestanden**.
7. **Een stabiliteitsbelofte**: schrijf op wat 1.0 omvat en vertraag de releases.

### 5.2 Kritieke ontbrekende schakels

1. **Het verhaal over gelijktijdigheid**: synchroon als uitgesproken keuze, instelbaar, met een regel voor lange
   I/O en een standpunt over free-threaded Python.
2. **De uitgaande HTTP-client** met time-outs, herhaling en een nepserver.
3. **OpenTelemetry-export.**
4. **De grens van de datalaag**: "Spring Data JDBC, niet JPA" als harde lijn, plus één nooduitgang voor dynamische
   queries. Beslis #15 en #16 in dat licht.
5. **De outbox beheren**: tonen, opnieuw aanbieden, opruimen, en documenteren wat over volgorde gegarandeerd is.
6. **Bestuur**: een tweede onderhouder en een tweede productieapplicatie buiten de eigen kring. Zonder die twee
   neemt geen team dit op, hoe goed de code ook is.
7. **Een conformiteitssuite voor bindings**: de tests die een binding moet halen. Goedkoper dan een tweede binding,
   en het maakt de claim controleerbaar.

### 5.3 Alternatieve bindings

| Binding | Oordeel |
|---|---|
| **MCP** (nieuwe inkomende adapter) | De enige die nieuwe gebruikers oplevert. Bouwen. |
| **Valkey** | Werkt met de Redis-client: testen en documenteren, bijna gratis. |
| **Litestar, BlackSheep** | Niet bouwen. Maanden werk, geen enkele gebruiker erbij. De conformiteitssuite volstaat als bewijs. |
| **SQLModel** | Zinloos: het is SQLAlchemy. |
| **asyncpg** | Botst met het synchrone model. |
| **psycopg zonder ORM** | Inhoudelijk interessant: het past bij "Spring Data JDBC", haalt de zwaarste afhankelijkheid weg en maakt de JPA-valkuil onmogelijk. Niet nu, wel de juiste tweede databinding als er ooit één komt. |
| **Kafka, NATS** | Geen binding maar een nieuw feature-package. Pas wanneer twee applicaties het vragen; `@externalized` eerst. |

### 5.4 De killer feature

**Eén use case, drie ingangen, één teststijl**: REST, berichten en MCP op dezelfde use case, elk met rollen,
transacties en sporen, en elk getest met dezelfde `@application_test`. Kort: *de plek waar een backend voor agents
even testbaar en even betrouwbaar is als een Spring Boot-service*.

Waarom dit en niet iets anders:

* het gebruikt wat al het sterkste is (de tests, de outbox, de grenzen) in plaats van iets nieuws te beginnen;
* het richt zich op een markt die nu ontstaat en waar nog geen gevestigde orde is, in plaats van FastAPI of Django
  frontaal aan te vallen;
* het is geloofwaardig vanuit de eigen praktijk: Subsidar doet het al.

Het risico: MCP is een bewegend doel, en een dunne binding is de enige verdediging. En de killer feature voor
*verspreiding* is geen feature maar de tweelingtutorial: het onderwijs is het kanaal waarlangs dit project gebruikers
krijgt.
