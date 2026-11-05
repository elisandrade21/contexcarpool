# Settlement rules R14-R15 as SPARQL 1.1 Update operations, run on both phones after the trip.
# Each phone asserts a wm:TripRecord with the distance it recorded; both phones exchange the two records
# and run these rules, so they compute the same final fare (or the same dispute) and can check each other.
# The fare is the agreed price per km times the mean recorded distance, capped at the booked trip,
# rounded to cents. Records that differ by more than 5% of the trip are flagged instead.

PREFIX wm:   <http://example.org/ridesharing#>
PREFIX prov: <http://www.w3.org/ns/prov#>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
INSERT {
  ?a wm:hasFinalFare ?fare .
  ?f a wm:RuleFiring, prov:Activity ; prov:used ?a, ?rp, ?rd ; prov:qualifiedAssociation ?q .
  ?q a prov:Association ; prov:agent wm:Reasoner ; prov:hadPlan wm:R14 .
  ?e a wm:InferredFact, prov:Entity ; prov:wasGeneratedBy ?f ; prov:wasDerivedFrom ?a, ?rp, ?rd ; rdf:value ?fare .
}
WHERE {
  ?rp a wm:TripRecord ; wm:ofOffer ?a ; wm:recordedBy "passenger" ; wm:hasTravelledKm ?kp .
  ?rd a wm:TripRecord ; wm:ofOffer ?a ; wm:recordedBy "driver" ; wm:hasTravelledKm ?kd .
  ?a wm:hasPricePerKm ?ppk ; wm:hasDistance ?D .
  FILTER(ABS(xsd:double(?kp) - xsd:double(?kd)) <= 5.0e-2 * xsd:double(?D))
  BIND((xsd:double(?kp) + xsd:double(?kd)) / 2.0e0 AS ?k)
  BIND(xsd:double(?ppk) * IF(?k < xsd:double(?D), ?k, xsd:double(?D)) AS ?raw)
  BIND(ROUND(?raw * 1.0e2) / 1.0e2 AS ?fare)
  BIND(IRI(CONCAT(STR(?a), "-R14-firing")) AS ?f)
  BIND(IRI(CONCAT(STR(?a), "-R14-association")) AS ?q)
  BIND(IRI(CONCAT(STR(?a), "-R14-fact")) AS ?e)
} ;

INSERT {
  ?a wm:hasContextNote wm:FareDisputed .
  ?f a wm:RuleFiring, prov:Activity ; prov:used ?a, ?rp, ?rd ; prov:qualifiedAssociation ?q .
  ?q a prov:Association ; prov:agent wm:Reasoner ; prov:hadPlan wm:R15 .
  ?e a wm:InferredFact, prov:Entity ; prov:wasGeneratedBy ?f ; prov:wasDerivedFrom ?a, ?rp, ?rd ; rdf:value wm:FareDisputed .
}
WHERE {
  ?rp a wm:TripRecord ; wm:ofOffer ?a ; wm:recordedBy "passenger" ; wm:hasTravelledKm ?kp .
  ?rd a wm:TripRecord ; wm:ofOffer ?a ; wm:recordedBy "driver" ; wm:hasTravelledKm ?kd .
  ?a wm:hasDistance ?D .
  FILTER(ABS(xsd:double(?kp) - xsd:double(?kd)) > 5.0e-2 * xsd:double(?D))
  BIND(IRI(CONCAT(STR(?a), "-R15-firing")) AS ?f)
  BIND(IRI(CONCAT(STR(?a), "-R15-association")) AS ?q)
  BIND(IRI(CONCAT(STR(?a), "-R15-fact")) AS ?e)
}
