# Instalação e configuração do ILIAS-Check com Telegram

[English](INSTALL.md) | **Português do Brasil** | [Deutsch](INSTALL.de.md)

Este guia acompanha a instalação do começo ao fim em Linux: preparar o Python,
configurar o acesso ao ILIAS, criar um bot, preencher as credenciais, testar e
manter o worker e o monitor funcionando.

**Os exemplos não contêm credenciais reais.** Substitua todos os campos indicados
antes de iniciar. A criação deste guia não executa serviços, altera o cron nem
envia mensagens. As etapas de ativação abaixo são ações que você executará
quando estiver pronto para permitir os acessos e envios descritos.

## 1. Entenda os dois processos

| Processo | O que faz | Quando executa |
| --- | --- | --- |
| `ilias-check bot` | Recebe comandos no chat privado e consulta as observações salvas. Um pedido de material pode iniciar uma nova verificação no ILIAS. | Continuamente, como worker. |
| `ilias-check monitor` | Verifica o ILIAS, atualiza o estado e envia notificações habilitadas. | Uma vez por chamada; o cron pode executar a cada 12 horas. |

**Iniciar somente o worker não cria um agendamento de coleta.** Os dois processos
devem usar a mesma conta Linux, o mesmo arquivo de configuração e os mesmos
diretórios de estado/cache. Não execute dois workers para o mesmo bot.

Pré-requisitos:

- Linux com Python **3.11 ou superior**, `venv`, `pip` e Git.
- Acesso HTTPS ao ILIAS e a `api.telegram.org`; não é necessário abrir uma porta
  pública nem configurar um webhook.
- Conta ILIAS autorizada e compatível com o login por usuário/senha implementado.
  A compatibilidade inicial é com ILIAS 9.23; SSO/MFA e outros layouts podem
  exigir adaptação.
- Conta pessoal do Telegram. Este software trabalha com **chat privado** e um
  único usuário autorizado, não com grupos ou canais.
- Para execução contínua, uma máquina que permaneça ligada. O serviço opcional
  deste guia usa systemd de usuário; o agendamento usa cron.

A instalação usa esta estrutura:

```text
/opt/ilias/
├── venv/   # ambiente virtual Python e executáveis
├── check/  # checkout do software (branch main)
└── data/   # configuração privada e dados de execução
    ├── ilias.env
    ├── inventory.json
    ├── monitor/     # estado SQLite
    ├── support/     # documentos baixados e manifesto
    └── monitor.log
```

Os arquivos de dados são criados nas etapas correspondentes. `data` fica fora do
checkout `check`. Use a mesma conta Linux comum em toda a instalação e execução;
`sudo` só é necessário para preparar `/opt/ilias` (e, opcionalmente, o *linger*).

## 2. Baixe e instale o software

Confira o Python:

```sh
python3 --version
```

O resultado precisa ser 3.11 ou superior. Em Debian/Ubuntu, instale `git`, `python3`,
`python3-venv` e `python3-pip` se necessário; confira a versão da distribuição.

Para uma **instalação nova**, prepare o diretório para o usuário atual. Execute
em uma sessão desse usuário comum, não em um shell de root:

```sh
sudo install -d -m 755 -o "$(id -un)" -g "$(id -gn)" /opt/ilias
git clone --branch main \
  https://github.com/richmont/ILIAS-Check.git /opt/ilias/check
python3 -m venv /opt/ilias/venv
cd /opt/ilias/check
/opt/ilias/venv/bin/python -m pip install -e '.[test]'
/opt/ilias/venv/bin/ilias-check --help
/opt/ilias/venv/bin/pytest -q
```

A implementação já foi integrada à `main`. Se já possui uma instalação, preserve
seus arquivos e use a seção de atualização; não clone sobre um checkout existente
nem altere o proprietário de uma instalação de outro usuário.

A ajuda deve listar `collect`, `classify`, `monitor` e `bot`. Os testes são offline
e não exigem credenciais reais. Não é necessário ativar o venv no shell: os
exemplos usam os executáveis de `/opt/ilias/venv` diretamente.

## 3. Prepare os arquivos privados

Ainda na pasta do projeto:

```sh
umask 077
install -d -m 700 "/opt/ilias/data"
install -d -m 700 "/opt/ilias/data/monitor"
install -d -m 700 "/opt/ilias/data/support"
```

Para a **primeira instalação**, copie o modelo inicial:

```sh
install -m 600 examples/config/ilias-local.env.example \
  /opt/ilias/data/ilias.env
```

Esse último comando substitui um arquivo existente. Se você já tem uma
configuração, edite-a e compare os modelos; não execute a cópia por cima dela.
Abra o arquivo no editor de sua preferência, por exemplo:

```sh
nano /opt/ilias/data/ilias.env
```

Há dois modelos completos no repositório:

- [ilias-local.env.example](examples/config/ilias-local.env.example): preparação e
  coleta inicial, com Telegram desativado.
- [ilias-telegram.env.example](examples/config/ilias-telegram.env.example): referência
  para a etapa de ativação do Telegram, ainda sem anexos automáticos.

Use **um único arquivo privado** `ilias.env` para a execução normal. Os modelos
são alternativas completas, não arquivos a carregar em sequência. O parâmetro
`--env-file` recebe somente um arquivo e não procura outros `.env` automaticamente.
Variáveis já definidas no ambiente do processo prevalecem sobre o arquivo.
Não use `source ilias.env`; o programa lê o formato dotenv diretamente.

## 4. Configure o ILIAS antes de iniciar

Preencha esta parte do arquivo privado:

```dotenv
# Exemplo: troque a URL e todos os valores REPLACE.
ILIAS_BASE_URL=https://ilias.example.edu
ILIAS_CLIENT_ID=REPLACE_CLIENT_ID
ILIAS_USER='REPLACE_USUARIO_ILIAS'
ILIAS_PASS='REPLACE_SENHA_ILIAS'
ILIAS_PENDING_ROOTS=1001,1002
ILIAS_TIMEZONE=Europe/Berlin

ILIAS_TIMEOUT_SECONDS=20
ILIAS_PENDING_MAX_DEPTH=12
ILIAS_PENDING_MAX_REQUESTS=500
ILIAS_PENDING_EXCLUDE_EXERCISES=
ILIAS_PENDING_ALTERNATIVE_SETS={}
ILIAS_PENDING_INCLUDE_CONTEXTUAL=false

ILIAS_PENDING_DOWNLOAD_SUPPORT=false
ILIAS_PENDING_OUTPUT_DIR=/opt/ilias/data/support
ILIAS_SUPPORT_MAX_FILE_BYTES=20971520
ILIAS_SUPPORT_MAX_RUN_BYTES=104857600
ILIAS_SUPPORT_REVALIDATE_HOURS=12
ILIAS_SUPPORT_CACHE_MAX_BYTES=200000000
ILIAS_SUPPORT_NO_DEADLINE_TTL_HOURS=168
ILIAS_SUPPORT_RETENTION_MAX_HOURS=

ILIAS_TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_ALLOWED_USER_ID=
ILIAS_TELEGRAM_SEND_DOCUMENTS=false
ILIAS_TELEGRAM_MAX_DOCUMENT_BYTES=20971520
ILIAS_TELEGRAM_MAX_MESSAGE_CHARS=4000
ILIAS_MONITOR_STATE_DIR=/opt/ilias/data/monitor
ILIAS_PENDING_REMINDER_HOURS=0
```

| Campo | Como preencher |
| --- | --- |
| `ILIAS_BASE_URL` | URL HTTPS da instalação, incluindo o subdiretório se existir, sem `login.php`, query string ou token de sessão. Exemplo: `https://ilias.example.edu/ilias`. |
| `ILIAS_CLIENT_ID` | Identificador da instalação; pode aparecer como `client_id` na URL de login. Não é seu usuário. Não o invente se estiver ausente: confirme com a instalação. |
| `ILIAS_USER`, `ILIAS_PASS` | Usuário e senha autorizados do ILIAS. Aspas ajudam a preservar espaços e `#`; respeite a sintaxe dotenv ao usar aspas dentro do valor. |
| `ILIAS_PENDING_ROOTS` | IDs reais das pastas/cursos a inspecionar. Em `goto.php?target=fold_1001`, a referência é `1001`; em uma URL com `ref_id=1002`, é `1002`. Os números acima são fictícios. |
| `ILIAS_TIMEZONE` | Fuso da instalação. Para Bonn/Alemanha, use `Europe/Berlin`, incluindo as regras de horário de verão. Não depende do fuso do seu computador. |

Mantenha os diretórios de estado e cache fora de qualquer checkout Git, sem
componentes simbólicos, com proprietário correto e permissões privadas. A quota
padrão do cache é **200 MB decimais**; o bot não pode alterá-la.

Não cole senhas/tokens em comandos, issues ou prints. O arquivo de credenciais
fica no host, não no Git. Confira a permissão sem mostrar seu conteúdo:

```sh
chmod 600 /opt/ilias/data/ilias.env
stat -c '%a %n' /opt/ilias/data/ilias.env
```

O resultado deve começar com `600`.

## 5. Crie o bot no Telegram e guarde o token

1. Abra o [BotFather oficial](https://t.me/BotFather) no Telegram.
2. Envie `/newbot`, escolha um nome e um username disponível terminado em `bot`.
3. Copie o token fornecido pelo BotFather para `TELEGRAM_BOT_TOKEN` no seu arquivo
   privado. Continue com `ILIAS_TELEGRAM_ENABLED=false`.
4. Abra o chat privado do bot criado e envie `/start`. Neste ponto ainda não haverá
   resposta: o worker não foi iniciado.

Exemplo dos campos nessa etapa:

```dotenv
ILIAS_TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN='REPLACE_TOKEN_REAL_DO_BOTFATHER'
TELEGRAM_CHAT_ID=
TELEGRAM_ALLOWED_USER_ID=
ILIAS_TELEGRAM_SEND_DOCUMENTS=false
```

O procedimento de criação e gerenciamento está na
[documentação oficial do BotFather](https://core.telegram.org/bots/features#botfather).
O token é uma credencial, não o username público do bot. Se ele for exposto,
revogue-o no BotFather, substitua o valor local e reinicie os processos envolvidos.

## 6. Obtenha os IDs sem iniciar o worker

Você precisa de dois IDs numéricos: o chat privado de destino e o usuário
permitido. Use a API do seu próprio bot; não precisa fornecer seus dados a um
bot de terceiros.

Com o worker ainda **parado**, envie novamente `/start` no chat privado do bot.
Execute este trecho na pasta do projeto. Ele lê o token do arquivo privado,
não o coloca no histórico do shell e não imprime conteúdo de mensagens:

```sh
/opt/ilias/venv/bin/python - <<'PY'
from pathlib import Path
import requests
from ilias_check.config import load_environment

values = load_environment(Path('/opt/ilias/data/ilias.env'))
token = (values.get('TELEGRAM_BOT_TOKEN') or '').strip()
if not token or 'REPLACE' in token:
    raise SystemExit('Preencha TELEGRAM_BOT_TOKEN no arquivo privado primeiro.')

def api(method, payload):
    try:
        with requests.post(
            f'https://api.telegram.org/bot{token}/{method}',
            json=payload, timeout=(10, 35), allow_redirects=False,
        ) as response:
            status = response.status_code
            result = response.json()
    except Exception:
        raise SystemExit('Falha ao consultar o Telegram; token e resposta foram omitidos.') from None
    if status != 200 or not isinstance(result, dict) or not result.get('ok'):
        raise SystemExit(f'Telegram recusou a consulta (HTTP {status}). Confira token, webhook e outros workers.')
    return result['result']

if api('getWebhookInfo', {}).get('url'):
    raise SystemExit('Há um webhook ativo. Use um bot dedicado ou desative a integração anterior antes de continuar.')
updates = api('getUpdates', {'timeout': 0, 'limit': 100, 'allowed_updates': ['message']})
seen = set()
for update in updates:
    message = update.get('message', {})
    chat = message.get('chat', {})
    sender = message.get('from', {})
    if chat.get('type') != 'private' or sender.get('is_bot'):
        continue
    pair = (chat.get('id'), sender.get('id'))
    if None in pair or pair in seen:
        continue
    seen.add(pair)
    print(f'TELEGRAM_CHAT_ID={pair[0]}')
    print(f'TELEGRAM_ALLOWED_USER_ID={pair[1]}')
if not seen:
    print('Nenhuma mensagem privada encontrada. Envie /start ao bot e tente novamente.')
PY
```

Copie o par correspondente à **sua própria conversa** para o arquivo privado.
Não use IDs de grupos/canais ou o ID do próprio bot. Se houver mais de um par,
confirme qual é o seu antes de configurar o usuário autorizado.

O script não envia mensagens e não avança o `offset` de recebimento. Não execute
essa consulta enquanto outro consumidor estiver usando `getUpdates`. Webhooks e
long polling são alternativas; para um bot reutilizado, migre a integração anterior
conscientemente antes de usar este worker. Referências:
[getUpdates](https://core.telegram.org/bots/api#getupdates) e
[getWebhookInfo](https://core.telegram.org/bots/api#getwebhookinfo).

## 7. Teste a coleta e grave a primeira observação, sem Telegram

Confirme que `ILIAS_TELEGRAM_ENABLED=false` e que os campos do ILIAS estão corretos.
Os comandos desta etapa acessam o ILIAS; nenhum deles deve enviar mensagens ao Telegram.

Primeiro, salve um inventário privado:

```sh
cd /opt/ilias/check
umask 077
/opt/ilias/venv/bin/ilias-check collect \
  --env-file /opt/ilias/data/ilias.env \
  > "/opt/ilias/data/inventory.json"
```

Depois, consulte os casos inconclusivos localmente:

```sh
/opt/ilias/venv/bin/ilias-check classify \
  --env-file /opt/ilias/data/ilias.env \
  --input "/opt/ilias/data/inventory.json" \
  --select needs-verification
```

O código de saída `2` indica resultado parcial e pode ser esperado para páginas
não resolvidas. Não significa necessariamente falha de login. Corrija erros fatais
antes de prosseguir; mantenha incertezas como incertezas.

Agora execute o monitor **com Telegram ainda desativado**, para gravar observações
no SQLite compartilhado com o worker:

```sh
/opt/ilias/venv/bin/ilias-check monitor \
  --env-file /opt/ilias/data/ilias.env
```

Isso pode deixar alertas na fila, mas não os envia enquanto o Telegram estiver
desativado. **`collect` sozinho não alimenta o histórico do bot, e `monitor --dry-run`
não grava essas observações.** Não pule a primeira execução normal do monitor.

## 8. Habilite o Telegram e valide a configuração antes de iniciar

No **mesmo arquivo privado**, substitua os campos existentes; não acrescente
linhas duplicadas nem sobrescreva suas credenciais do ILIAS com placeholders:

```dotenv
ILIAS_TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN='REPLACE_TOKEN_REAL_DO_BOTFATHER'
TELEGRAM_CHAT_ID=REPLACE_CHAT_ID_NUMERICO
TELEGRAM_ALLOWED_USER_ID=REPLACE_USER_ID_NUMERICO
ILIAS_TELEGRAM_SEND_DOCUMENTS=false
```

O [modelo de ativação](examples/config/ilias-telegram.env.example) mostra o arquivo
completo. Os IDs devem ser inteiros positivos sem `@`, username ou prefixo de grupo.
Manter `ILIAS_TELEGRAM_SEND_DOCUMENTS=false` permite começar somente com texto e links.

Valide a configuração, **sem rede e sem iniciar o worker**:

```sh
/opt/ilias/venv/bin/python - <<'PY'
from pathlib import Path
from ilias_check.config import CollectorConfig, ConfigurationError, load_environment
from ilias_check.cache_config import CacheError, boolean
from ilias_check.telegram import TelegramConfig

path = Path('/opt/ilias/data/ilias.env')
try:
    values = load_environment(path)
    required = ('ILIAS_BASE_URL', 'ILIAS_CLIENT_ID', 'ILIAS_USER', 'ILIAS_PASS',
                'ILIAS_PENDING_ROOTS')
    if any('REPLACE' in str(values.get(key, '')) for key in required):
        raise ConfigurationError('Ainda há campos REPLACE na configuração.')
    CollectorConfig.from_mapping(values)
    enabled = boolean(values, 'ILIAS_TELEGRAM_ENABLED')
    if enabled:
        telegram = ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'TELEGRAM_ALLOWED_USER_ID')
        if any('REPLACE' in str(values.get(key, '')) for key in telegram):
            raise ConfigurationError('Ainda há campos REPLACE na configuração do Telegram.')
        TelegramConfig.from_mapping(values, worker=True)
except (ConfigurationError, CacheError) as exc:
    raise SystemExit(f'Configuração inválida: {exc}') from None
print(f"Configuração válida (Telegram {'ativo' if enabled else 'desativado'}). Nenhuma conexão foi realizada.")
PY
```

Essa validação confere o formato, não autentica credenciais nem comprova que os IDs
pertencem a você. Confirme essa identidade antes do teste real. Enquanto
`ILIAS_TELEGRAM_ENABLED=false`, ela valida somente as configurações do ILIAS/coletor;
as verificações do worker rodam quando o Telegram é habilitado, então o mesmo bloco
pode ser usado antes desta etapa.

Você também pode simular o monitor:

```sh
/opt/ilias/venv/bin/ilias-check monitor \
  --env-file /opt/ilias/data/ilias.env \
  --dry-run
```

Ele pode acessar o ILIAS e manter o cache local conforme a configuração, mas não
chama o Telegram nem confirma notificações como entregues.

## 9. Faça a primeira execução real do bot

**Esta etapa habilita comunicação real com o Telegram.** Com os dados conferidos,
inicie o worker em primeiro plano:

```sh
/opt/ilias/venv/bin/ilias-check bot \
  --env-file /opt/ilias/data/ilias.env
```

Deixe esse terminal aberto. No chat privado do bot, envie `/start` e `/pendentes`.
Ele deve responder em português, com títulos/instruções originais do ILIAS e
horários das observações. `/verificar` deve conservar os casos inconclusivos.
Não interprete uma lista vazia como conclusão de todas as tarefas.

Comandos iniciais:

| Comando | Resultado esperado |
| --- | --- |
| `/ajuda` | Ajuda e navegação. |
| `/pendentes` | Uploads pendentes confirmados. |
| `/entregues` | Histórico de entregas; não presume aprovação. |
| `/encerradas` | Encerradas sem entrega. |
| `/verificar` | Inconclusivas, fonte e convite a feedback. |
| `/configuracoes` | Retenção e uso/quota do cache. |
| `/materiais` | Materiais selecionáveis; tocar em um autoriza o envio daquela cópia pelo Telegram. |
| `/relatar` | Relato revisável sobre o software; nenhuma issue é aberta automaticamente. |

Mesmo com anexos **automáticos** desativados, um pedido explícito em `/materiais`
pode baixar e enviar o material escolhido. Não toque nessa ação se ainda não
quiser transmitir documentos. O bot não baixa arquivos que você enviar como resposta.

Para testar notificações, em **outro terminal** execute:

```sh
cd /opt/ilias/check
/opt/ilias/venv/bin/ilias-check monitor \
  --env-file /opt/ilias/data/ilias.env
```

Essa execução pode enviar os alertas pendentes da fila — não é necessariamente
uma única mensagem. Verifique o destinatário, os links e as qualificações de
cobertura. Repetições normais sem mudanças não devem reenviar os mesmos alertas;
um timeout ambíguo pode resultar em duplicatas numa tentativa posterior.

Se quiser sugestões de comandos no Telegram, use `/setcommands` no BotFather,
selecione seu bot e envie, por exemplo:

```text
start - Iniciar
ajuda - Ajuda
pendentes - Tarefas pendentes
entregues - Historico de entregas
encerradas - Encerradas sem entrega
verificar - Casos inconclusivos
materiais - Materiais de apoio
configuracoes - Retencao e armazenamento
relatar - Relatar problema no software
cancelar - Cancelar dialogo
```

Isso configura apenas sugestões; a autorização continua sendo verificada pelo
software. Consulte [comandos do Telegram](https://core.telegram.org/bots/features#commands).

Ao terminar o teste em primeiro plano, use **Ctrl+C** para parar o worker antes
de iniciar o serviço da próxima etapa.

## 10. Mantenha o worker ativo com systemd de usuário

Esta etapa é opcional para testes, mas útil em um host que ficará ligado.
Execute como o mesmo usuário Linux usado na configuração e na coleta.
Não rode simultaneamente o worker manual e o serviço.

Crie `~/.config/systemd/user/ilias-check-bot.service`:

```sh
mkdir -p "$HOME/.config/systemd/user"
nano "$HOME/.config/systemd/user/ilias-check-bot.service"
```

Conteúdo completo:

```ini
[Unit]
Description=ILIAS-Check private Telegram worker
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=simple
WorkingDirectory=/opt/ilias/check
ExecStart=/opt/ilias/venv/bin/ilias-check bot --env-file /opt/ilias/data/ilias.env
UMask=0077
Restart=on-failure
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

Os caminhos absolutos seguem a estrutura `/opt/ilias`. Se escolher outro local,
ajuste `WorkingDirectory` e `ExecStart`. O `.env` é lido pelo programa
via `--env-file`; não é necessário um `EnvironmentFile` adicional.
Referência: [unidades e especificadores do systemd](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html#Specifiers).

Ative e confira:

```sh
systemctl --user daemon-reload
systemctl --user enable --now ilias-check-bot.service
systemctl --user status ilias-check-bot.service
journalctl --user -u ilias-check-bot.service -n 50 --no-pager
```

O serviço deve aparecer como `active (running)`. Verifique também uma resposta
real a `/ajuda`; somente o estado do processo não comprova o funcionamento do chat.
Para alterações futuras no `.env`, reinicie o worker:

```sh
systemctl --user restart ilias-check-bot.service
```

Para manter o gerenciador de usuário ativo após logout e iniciá-lo no boot, um
administrador pode habilitar *linger* para sua conta:

```sh
sudo loginctl enable-linger SEU_USUARIO_LINUX
```

Troque o placeholder pelo usuário real do host, não pelo username do Telegram.
Essa opção modifica o comportamento de inicialização da conta; use-a somente se
quiser esse serviço contínuo. Veja [loginctl](https://www.freedesktop.org/software/systemd/man/latest/loginctl.html).
Sem systemd de usuário, mantenha o worker em primeiro plano ou use o supervisor
do seu ambiente com o mesmo executável, usuário e arquivo de configuração.

## 11. Agende as verificações a cada 12 horas

O serviço acima recebe comandos; a atualização periódica é responsabilidade do
monitor. O cron deve estar disponível e ativo no host. Prepare um log privado:

```sh
touch "/opt/ilias/data/monitor.log"
chmod 600 "/opt/ilias/data/monitor.log"
crontab -e
```

Acrescente esta linha ao crontab do mesmo usuário que executa o worker:

```cron
0 */12 * * * /opt/ilias/venv/bin/ilias-check monitor --env-file /opt/ilias/data/ilias.env >> /opt/ilias/data/monitor.log 2>&1
```

Confira com:

```sh
crontab -l
```

O exemplo roda às 00h e 12h no fuso do agendador/host. `ILIAS_TIMEZONE=Europe/Berlin`
controla a interpretação dos prazos do ILIAS, não muda o fuso do cron. Não é preciso
manter um shell com venv ativado: a linha usa o executável absoluto.

O monitor impede sobreposição para a mesma conta/estado. Uma invocação que encontre
a execução anterior em andamento pode sair com código `3`; não inicie novos workers
para tentar contornar o lock. Confira o log e aguarde a próxima execução.

`ILIAS_PENDING_REMINDER_HOURS=0` desativa lembretes repetidos: a coleta a cada 12 horas
não implica uma mensagem a cada 12 horas. Para lembretes opcionais diários, configure
`ILIAS_PENDING_REMINDER_HOURS=24`; alterações relevantes continuam podendo gerar alertas.

## 12. Ative materiais somente se desejar

Há três controles diferentes:

| Objetivo | Configuração/ação |
| --- | --- |
| Notificações com texto e links | `ILIAS_TELEGRAM_ENABLED=true`, `ILIAS_TELEGRAM_SEND_DOCUMENTS=false`. |
| Cache local automático de apoio elegível | `ILIAS_PENDING_DOWNLOAD_SUPPORT=true`. Isso sozinho não autoriza envio pelo Telegram. |
| Anexos automáticos nas notificações | `ILIAS_PENDING_DOWNLOAD_SUPPORT=true` e `ILIAS_TELEGRAM_SEND_DOCUMENTS=true`, após consentir com a transmissão dos documentos. |
| Envio de um material escolhido | Ação explícita de download em `/materiais`, sem habilitar anexos automáticos futuros. |

Para cache local, edite os campos existentes:

```dotenv
ILIAS_PENDING_DOWNLOAD_SUPPORT=true
ILIAS_PENDING_OUTPUT_DIR=/opt/ilias/data/support
ILIAS_TELEGRAM_SEND_DOCUMENTS=false
```

Somente se também quiser anexos automáticos:

```dotenv
ILIAS_TELEGRAM_SEND_DOCUMENTS=true
```

Reinicie o worker após editar o arquivo e faça uma verificação manual antes de
confiar no agendamento. Uma notificação já concluída não é necessariamente reenviada
apenas por mudar a preferência de anexos.

O limite padrão é 20 MiB por arquivo, 100 MiB por execução e 200 MB decimais no cache.
Prazos/entregas confirmadas encerram associações; sem prazo, a retenção padrão é de
168 horas. O bot permite retenção em `/configuracoes`, mas não altera quota nem oferece
limpeza manual. Cópias já recebidas pelo Telegram não podem ser revogadas pela limpeza
local. Veja [o ciclo do cache](docs/support-cache.md).

## 13. Pare, atualize ou faça backup

Para parar e impedir a inicialização automática do worker:

```sh
systemctl --user disable --now ilias-check-bot.service
```

Remova/comente também a linha do monitor em `crontab -e` se quiser interromper as
verificações agendadas. Definir `ILIAS_TELEGRAM_ENABLED=false` afeta novas invocações;
um worker já em execução mantém a configuração carregada até ser parado/reiniciado.
Nenhuma dessas ações entrega respostas ou modifica atividades no ILIAS.

Antes de atualizar o código ou copiar o SQLite para backup, pause o worker e o
agendamento e espere uma coleta em andamento terminar. Preserve o `.env`, o diretório
de estado e suas permissões privadas. Apagar o estado perde histórico/deduplicação e
pode gerar alertas iniciais novamente. O cache é descartável, não uma fonte oficial.

Com os processos parados, atualize a `main`. Se o checkout ainda estiver na antiga
branch de desenvolvimento, o comando `switch` abaixo seleciona a branch integrada:

```sh
cd /opt/ilias/check
git fetch origin
git switch main
git pull --ff-only origin main
/opt/ilias/venv/bin/python -m pip install -e '.[test]'
/opt/ilias/venv/bin/pytest -q
```

Se houver mudanças locais ou instruções de migração na versão nova, resolva-as antes
de continuar. Depois de conferir a configuração, reative o worker e restaure o
agendamento que você havia pausado.

## Diagnóstico rápido

| Sintoma | O que conferir |
| --- | --- |
| O bot não responde | Serviço/terminal ativo, `ILIAS_TELEGRAM_ENABLED=true`, token, IDs e chat privado. Envie um comando novo após reiniciar. |
| Consulta de IDs vazia | Envie `/start` ao bot correto; pare outros consumidores antes de repetir a consulta. |
| Telegram HTTP 401 | Token incorreto ou revogado; substitua pelo token atual do BotFather. |
| Telegram HTTP 409/conflito | Outro worker/consumidor de `getUpdates` ou uma configuração de webhook. Não use a consulta de IDs em paralelo com o worker. |
| Telegram HTTP 403 | Bot bloqueado pelo destinatário ou chat sem acesso; confira o chat privado e inicie a conversa. |
| Lista sem dados após instalar | Execute `monitor` uma vez com o mesmo `.env` e estado; `collect` e `monitor --dry-run` não alimentam as consultas persistentes. |
| Código `2` / inconclusivo | Confira cobertura e `/verificar`; dados ausentes não provam entrega nem ausência de tarefas. |
| Erro de autenticação no ILIAS | URL base, client ID, usuário/senha e compatibilidade do formulário; não publique HTML ou credenciais para diagnosticar. |
| Erro de diretório privado | Proprietário, modo `0700`, caminho fora do Git e ausência de symlinks; arquivos gerenciados usam `0600`. |
| Valor do `.env` parece ignorado | Variáveis exportadas no processo prevalecem; o worker precisa de reinício após edição. Não imprima o ambiente inteiro para investigar. |
| Material não enviado | Consentimento, classificação atual, associação, prazo/TTL, integridade, tipo, tamanho e quota; use o link original se indisponível. |
| `systemctl --user` sem barramento | Sessão/gerenciador de usuário indisponível nesse ambiente; confira a sessão Linux ou use um supervisor apropriado. |

Instalação concluída significa: credenciais preenchidas e privadas, coleta local
conferida, owner/chat corretos, resposta a um comando real, monitor executado com
sucesso ou parcialidade compreendida, e worker/agendamento habilitados somente
quando desejados. Consulte também [operações do Telegram](docs/telegram.md) e
[o checklist de implantação](docs/deployment-checklist.md).
