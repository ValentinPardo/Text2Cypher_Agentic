// Constraint básicos
CREATE CONSTRAINT unique_producto IF NOT EXISTS FOR (p:Producto) REQUIRE p.sku IS UNIQUE;
CREATE CONSTRAINT unique_cliente IF NOT EXISTS FOR (c:Cliente) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT unique_categoria IF NOT EXISTS FOR (cat:Categoria) REQUIRE cat.nombre IS UNIQUE;
CREATE CONSTRAINT unique_compra IF NOT EXISTS FOR (o:Compra) REQUIRE o.id IS UNIQUE;

CREATE (cat1:Categoria {nombre:"Electrónica"});
CREATE (cat2:Categoria {nombre:"Computación"});
CREATE (cat3:Categoria {nombre:"Accesorios"});
CREATE (cat4:Categoria {nombre:"Hogar"});

CREATE (p1:Producto {
    sku:"NTB-A5-001",
    nombre:"Notebook Aspire 5",
    description:"Notebook de uso general con 8GB RAM y SSD de 512GB. Ideal para estudiantes.",
    precio: 750000,
    stock: 34
});

CREATE (p2:Producto {
    sku:"MON-27-IPS",
    nombre:"Monitor 27'' IPS",
    description:"Monitor 27 pulgadas IPS 144Hz ideal para oficinas y gaming casual.",
    precio: 320000,
    stock: 12
});

CREATE (p3:Producto {
    sku:"KB-RGB-001",
    nombre:"Teclado Mecánico RGB",
    description:"Teclado mecánico con switches blue y retroiluminación RGB.",
    precio: 82000,
    stock: 50
});

CREATE (p4:Producto {
    sku:"MSE-WL-02",
    nombre:"Mouse Wireless Logitech",
    description:"Mouse inalámbrico ergonómico ideal para oficina.",
    precio: 35000,
    stock: 80
});

CREATE (p5:Producto {
    sku:"CAF-HOME-01",
    nombre:"Cafetera Automática",
    description:"Cafetera automática con molinillo integrado y programable.",
    precio: 210000,
    stock: 15
});

MATCH (p:Producto {sku:"NTB-A5-001"}), (c:Categoria {nombre:"Computación"}) MERGE (p)-[:PERTENECE_A]->(c);
MATCH (p:Producto {sku:"MON-27-IPS"}), (c:Categoria {nombre:"Electrónica"}) MERGE (p)-[:PERTENECE_A]->(c);
MATCH (p:Producto {sku:"KB-RGB-001"}), (c:Categoria {nombre:"Computación"}) MERGE (p)-[:PERTENECE_A]->(c);
MATCH (p:Producto {sku:"MSE-WL-02"}), (c:Categoria {nombre:"Accesorios"}) MERGE (p)-[:PERTENECE_A]->(c);
MATCH (p:Producto {sku:"CAF-HOME-01"}), (c:Categoria {nombre:"Hogar"}) MERGE (p)-[:PERTENECE_A]->(c);

CREATE (:Review {
    text:"Muy buena notebook, rápida y silenciosa. Perfecta para estudiar.",
    rating: 5
})-[:RESEÑA_DE]->(p1);

CREATE (:Review {
    text:"Monitor con muy buena calidad de colores pero el soporte es débil.",
    rating: 4
})-[:RESEÑA_DE]->(p2);

CREATE (:Review {
    text:"El teclado es muy ruidoso pero las teclas responden bien.",
    rating: 3
})-[:RESEÑA_DE]->(p3);

CREATE (:Review {
    text:"Excelente mouse, batería eterna.",
    rating: 5
})-[:RESEÑA_DE]->(p4);

CREATE (:Review {
    text:"Hace buen café pero es difícil de limpiar.",
    rating: 4
})-[:RESEÑA_DE]->(p5);

CREATE (c1:Cliente {
    id: "CLI-001",
    nombre: "Juan Pérez",
    email: "juanperez@gmail.com"
});

CREATE (c2:Cliente {
    id: "CLI-002",
    nombre: "Ana López",
    email: "ana.lopez@gmail.com"
});

CREATE (c3:Cliente {
    id: "CLI-003",
    nombre: "Carlos Méndez",
    email: "carlosm@gmail.com"
});

// Compra 1 de Juan
CREATE (o1:Compra {
    id:"ORD-001",
    fecha: date("2025-01-15"),
    total: 750000
});
MATCH (c1:Cliente {id:"CLI-001"}) MERGE (c1)-[:REALIZO_COMPRA]->(o1);
MATCH (p1:Producto {sku:"NTB-A5-001"}) MERGE (o1)-[:INCLUYE {cantidad:1}]->(p1);

// Compra 2 de Ana
CREATE (o2:Compra {
    id:"ORD-002",
    fecha: date("2025-01-20"),
    total: 355000
});
MATCH (c2:Cliente {id:"CLI-002"}) MERGE (c2)-[:REALIZO_COMPRA]->(o2);
MATCH (p4:Producto {sku:"MSE-WL-02"}) MERGE (o2)-[:INCLUYE {cantidad:2}]->(p4);
MATCH (p3:Producto {sku:"KB-RGB-001"}) MERGE (o2)-[:INCLUYE {cantidad:1}]->(p3);

// Compra 3 de Carlos
CREATE (o3:Compra {
    id:"ORD-003",
    fecha: date("2025-01-25"),
    total: 530000
});
MATCH (c3:Cliente {id:"CLI-003"}) MERGE (c3)-[:REALIZO_COMPRA]->(o3);
MATCH (p2:Producto {sku:"MON-27-IPS"}) MERGE (o3)-[:INCLUYE {cantidad:1}]->(p2);
MATCH (p4:Producto {sku:"MSE-WL-02"}) MERGE (o3)-[:INCLUYE {cantidad:1}]->(p4);

MATCH (c:Compra)-[:INCLUYE]->(p:Producto)
WITH c, collect(p) as items
UNWIND items as p1
UNWIND items as p2
WITH p1, p2 WHERE p1 <> p2
MERGE (p1)-[r:SE_COMPRA_JUNTO]->(p2)
ON CREATE SET r.weight = 1
ON MATCH SET r.weight = r.weight + 1;

MATCH (p1:Producto)-[:PERTENECE_A]->(cat)<-[:PERTENECE_A]-(p2:Producto)
WHERE p1 <> p2
MERGE (p1)-[:SIMILAR {motivo:"categoria"}]->(p2);

MATCH (c:Cliente)-[r:REALIZO_COMPRA]->(o:Compra)
MERGE (c)-[:TIENE_HISTORIAL]->(o);
