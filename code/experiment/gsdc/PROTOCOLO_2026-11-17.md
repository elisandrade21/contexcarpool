# Protocolo: regra de tarifa (R14–R15) com GPS real de celulares (GSDC 2022)

Data: 17/11/2026. Regras fixadas **antes de abrir os dados**. Qualquer mudança depois disso vai para a seção "Desvios", com data e motivo.

## Dados
- Fonte: Google Smartphone Decimeter Challenge 2022 (Kaggle), conjunto de treino. Uso acadêmico permitido; os dados não são redistribuídos. Citar Fu, Khider e van Diggelen (ION GNSS+ 2020, doi 10.33012/2020.17628).
- Viagens: as 58 que têm dois ou mais celulares no mesmo carro.
- Posição do celular: a posição por mínimos quadrados ponderados (WLS) que o próprio conjunto fornece em `device_gnss.csv` (WlsPositionX/Y/ZEcefMeters), uma por época, convertida para latitude e longitude.
- Referência: `ground_truth.csv`, do equipamento de alta precisão. Faz o papel do odômetro.

## Distância de cada celular
O mesmo filtro do cliente do artigo (index.html), sem ajuste novo:
- só épocas com posição válida;
- descarta o salto que implicar velocidade acima de 55 m/s;
- só soma o passo se ele for maior que 5 m (o arquivo não traz a precisão por época, então vale o piso de 5 m do cliente);
- soma as distâncias pela fórmula de haversine.

## Trechos (corridas simuladas sobre trajetos reais)
- Cada viagem é cortada em trechos sem sobreposição de 2, 5 e 10 km de distância de referência, contados desde o início.
- **Desembarque antecipado:** para cada trecho, o passageiro desce numa fração sorteada entre 50% e 100% do trecho. A semente é fixa (20261117). O celular do passageiro mede até esse ponto, e o do motorista também (caso honesto).
- **Pares:** todo par de celulares diferentes da mesma viagem, nos mesmos instantes. Os pares são separados em "mesmo modelo" e "modelo diferente".

## Medidas
1. **Diferença entre celulares:** |d1 − d2| / média(d1, d2), em cada trecho. Reportar mediana, percentil 95 e máximo.
2. **Erro contra a referência:** |d − d_ref| / d_ref, por celular e trecho.
3. **Disputas falsas (caso honesto):** proporção de trechos em que a regra R15 dispararia, ou seja, |d1 − d2| > 5% da distância reservada (a distância de referência do trecho inteiro), exatamente como em rules_settlement.ru. O intervalo de 95% é calculado por bootstrap **por viagem**, porque os trechos de uma mesma viagem não são independentes.
4. **Detecção:** no mesmo par, o motorista declara o trecho inteiro e o passageiro declara o que o próprio celular mediu até o desembarque. Medir a proporção que R15 detecta.
5. **Sensibilidade:** tolerâncias de 3%, 5% e 10%, uma linha cada.

## Correção da regra (só se a regra de 5% falhar)
- "Falhar" significa: disputas falsas acima de 5% em algum tamanho de trecho.
- Nesse caso, as viagens são divididas ao acaso (semente 20261117) em dois grupos iguais, A e B.
- No grupo A, escolhe-se o X da regra "tolerância = máximo(5% da distância, X metros)", com X entre 50, 100, 200 e 300 m: o menor X que deixa as disputas falsas em até 5%.
- No grupo B, reporta-se o resultado com esse X, sem mexer mais em nada.

## O que será reportado no artigo, qualquer que seja o resultado
- O número de viagens, pares e trechos, e as medidas 1 a 4 para 5% de tolerância.
- As limitações: celulares no painel, a maioria em rodovias da Califórnia, posição WLS calculada pelo conjunto e não a localização final do Android.

## Desvios
Nenhum. A análise rodou uma única vez, em 18/11/2026, sobre os 332 arquivos (58 viagens, 177 pares). A regra de 5% passou do limite de 5% de disputas falsas em todos os tamanhos (5,3–5,6%); a correção "máximo(5%, X m)" não achou X ≤ 300 m no grupo A, então nada foi reportado no grupo B.
