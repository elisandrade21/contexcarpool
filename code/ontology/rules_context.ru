# Context rules R9-R13 as SPARQL 1.1 Update operations, run on the passenger's device.
# Distance is the equirectangular approximation, compared in squared metres because
# SPARQL 1.1 has neither square root nor trigonometry. R12 compares walking distance at
# 5 km/h (83.33 m/min) with the minutes left; R13 marks pickups beyond 5 km or too late on foot that a car at an illustrative 25 km/h (416.67 m/min) still reaches in time. The rules only add remarks to the
# rationale: they assert wm:hasContextNote and never touch the score or the order.
# Distances use xsd:double: products of xsd:decimal values overflow in some engines
# (Oxigraph), which would silently leave the rule unfired.

PREFIX wm:     <http://example.org/ridesharing#>
PREFIX prov:   <http://www.w3.org/ns/prov#>
PREFIX rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX schema: <https://schema.org/>
PREFIX xsd:    <http://www.w3.org/2001/XMLSchema#>
INSERT {
  ?a wm:hasContextNote wm:WalkablePickup .
  ?f a wm:RuleFiring, prov:Activity ; prov:used ?a, ?c ; prov:qualifiedAssociation ?q .
  ?q a prov:Association ; prov:agent wm:Reasoner ; prov:hadPlan wm:R9 .
  ?e a wm:InferredFact, prov:Entity ; prov:wasGeneratedBy ?f ; prov:wasDerivedFrom ?a, ?c ; rdf:value wm:WalkablePickup .
}
WHERE {
  ?c a wm:DeviceContext ; schema:latitude ?lat ; schema:longitude ?lon ;
     wm:hasCosLatitude ?cos ; wm:hasNowMinute ?now .
  ?a a wm:Travel ; wm:hasDepartureMinute ?dep ; wm:hasPickup ?p .
  ?p schema:latitude ?plat ; schema:longitude ?plon .
  BIND(1.1132e5 * (xsd:double(?plat) - xsd:double(?lat)) AS ?dy)
  BIND(1.1132e5 * xsd:double(?cos) * (xsd:double(?plon) - xsd:double(?lon)) AS ?dx)
  BIND(?dx * ?dx + ?dy * ?dy AS ?d2)
  BIND(?dep - ?now AS ?t)
  FILTER(?d2 <= 6.4e5)
  BIND(IRI(CONCAT(STR(?a), "-R9-firing")) AS ?f)
  BIND(IRI(CONCAT(STR(?a), "-R9-association")) AS ?q)
  BIND(IRI(CONCAT(STR(?a), "-R9-fact")) AS ?e)
} ;

INSERT {
  ?a wm:hasContextNote wm:DistantPickup .
  ?f a wm:RuleFiring, prov:Activity ; prov:used ?a, ?c ; prov:qualifiedAssociation ?q .
  ?q a prov:Association ; prov:agent wm:Reasoner ; prov:hadPlan wm:R10 .
  ?e a wm:InferredFact, prov:Entity ; prov:wasGeneratedBy ?f ; prov:wasDerivedFrom ?a, ?c ; rdf:value wm:DistantPickup .
}
WHERE {
  ?c a wm:DeviceContext ; schema:latitude ?lat ; schema:longitude ?lon ;
     wm:hasCosLatitude ?cos ; wm:hasNowMinute ?now .
  ?a a wm:Travel ; wm:hasDepartureMinute ?dep ; wm:hasPickup ?p .
  ?p schema:latitude ?plat ; schema:longitude ?plon .
  BIND(1.1132e5 * (xsd:double(?plat) - xsd:double(?lat)) AS ?dy)
  BIND(1.1132e5 * xsd:double(?cos) * (xsd:double(?plon) - xsd:double(?lon)) AS ?dx)
  BIND(?dx * ?dx + ?dy * ?dy AS ?d2)
  BIND(?dep - ?now AS ?t)
  FILTER(?d2 > 2.5e7)
  BIND(IRI(CONCAT(STR(?a), "-R10-firing")) AS ?f)
  BIND(IRI(CONCAT(STR(?a), "-R10-association")) AS ?q)
  BIND(IRI(CONCAT(STR(?a), "-R10-fact")) AS ?e)
} ;

INSERT {
  ?a wm:hasContextNote wm:DepartsSoon .
  ?f a wm:RuleFiring, prov:Activity ; prov:used ?a, ?c ; prov:qualifiedAssociation ?q .
  ?q a prov:Association ; prov:agent wm:Reasoner ; prov:hadPlan wm:R11 .
  ?e a wm:InferredFact, prov:Entity ; prov:wasGeneratedBy ?f ; prov:wasDerivedFrom ?a, ?c ; rdf:value wm:DepartsSoon .
}
WHERE {
  ?c a wm:DeviceContext ; schema:latitude ?lat ; schema:longitude ?lon ;
     wm:hasCosLatitude ?cos ; wm:hasNowMinute ?now .
  ?a a wm:Travel ; wm:hasDepartureMinute ?dep ; wm:hasPickup ?p .
  ?p schema:latitude ?plat ; schema:longitude ?plon .
  BIND(1.1132e5 * (xsd:double(?plat) - xsd:double(?lat)) AS ?dy)
  BIND(1.1132e5 * xsd:double(?cos) * (xsd:double(?plon) - xsd:double(?lon)) AS ?dx)
  BIND(?dx * ?dx + ?dy * ?dy AS ?d2)
  BIND(?dep - ?now AS ?t)
  FILTER(?t >= 0 && ?t <= 60)
  BIND(IRI(CONCAT(STR(?a), "-R11-firing")) AS ?f)
  BIND(IRI(CONCAT(STR(?a), "-R11-association")) AS ?q)
  BIND(IRI(CONCAT(STR(?a), "-R11-fact")) AS ?e)
} ;

INSERT {
  ?a wm:hasContextNote wm:MissableOnFoot .
  ?f a wm:RuleFiring, prov:Activity ; prov:used ?a, ?c ; prov:qualifiedAssociation ?q .
  ?q a prov:Association ; prov:agent wm:Reasoner ; prov:hadPlan wm:R12 .
  ?e a wm:InferredFact, prov:Entity ; prov:wasGeneratedBy ?f ; prov:wasDerivedFrom ?a, ?c ; rdf:value wm:MissableOnFoot .
}
WHERE {
  ?c a wm:DeviceContext ; schema:latitude ?lat ; schema:longitude ?lon ;
     wm:hasCosLatitude ?cos ; wm:hasNowMinute ?now .
  ?a a wm:Travel ; wm:hasDepartureMinute ?dep ; wm:hasPickup ?p .
  ?p schema:latitude ?plat ; schema:longitude ?plon .
  BIND(1.1132e5 * (xsd:double(?plat) - xsd:double(?lat)) AS ?dy)
  BIND(1.1132e5 * xsd:double(?cos) * (xsd:double(?plon) - xsd:double(?lon)) AS ?dx)
  BIND(?dx * ?dx + ?dy * ?dy AS ?d2)
  BIND(?dep - ?now AS ?t)
  FILTER(?t >= 0 && ?d2 > (8.333e1 * ?t) * (8.333e1 * ?t))
  BIND(IRI(CONCAT(STR(?a), "-R12-firing")) AS ?f)
  BIND(IRI(CONCAT(STR(?a), "-R12-association")) AS ?q)
  BIND(IRI(CONCAT(STR(?a), "-R12-fact")) AS ?e)
} ;

INSERT {
  ?a wm:hasContextNote wm:ReachableByCar .
  ?f a wm:RuleFiring, prov:Activity ; prov:used ?a, ?c ; prov:qualifiedAssociation ?q .
  ?q a prov:Association ; prov:agent wm:Reasoner ; prov:hadPlan wm:R13 .
  ?e a wm:InferredFact, prov:Entity ; prov:wasGeneratedBy ?f ; prov:wasDerivedFrom ?a, ?c ; rdf:value wm:ReachableByCar .
}
WHERE {
  ?c a wm:DeviceContext ; schema:latitude ?lat ; schema:longitude ?lon ;
     wm:hasCosLatitude ?cos ; wm:hasNowMinute ?now .
  ?a a wm:Travel ; wm:hasDepartureMinute ?dep ; wm:hasPickup ?p .
  ?p schema:latitude ?plat ; schema:longitude ?plon .
  BIND(1.1132e5 * (xsd:double(?plat) - xsd:double(?lat)) AS ?dy)
  BIND(1.1132e5 * xsd:double(?cos) * (xsd:double(?plon) - xsd:double(?lon)) AS ?dx)
  BIND(?dx * ?dx + ?dy * ?dy AS ?d2)
  BIND(?dep - ?now AS ?t)
  FILTER(?t >= 0 && (?d2 > 2.5e7 || ?d2 > (8.333e1 * ?t) * (8.333e1 * ?t)) && ?d2 <= (4.1667e2 * ?t) * (4.1667e2 * ?t))
  BIND(IRI(CONCAT(STR(?a), "-R13-firing")) AS ?f)
  BIND(IRI(CONCAT(STR(?a), "-R13-association")) AS ?q)
  BIND(IRI(CONCAT(STR(?a), "-R13-fact")) AS ?e)
}
