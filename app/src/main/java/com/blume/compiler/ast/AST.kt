package com.blume.compiler.ast

enum class OwnershipKind(val keyword: String) {
    AUTOMATIC("automatic"),
    OWNED("owned"),
    SHARED("shared"),
    WEAK("weak"),
    UNOWNED("unowned");

    companion object {
        fun fromString(s: String?): OwnershipKind {
            return when (s?.lowercase()) {
                "owned" -> OWNED
                "shared" -> SHARED
                "weak" -> WEAK
                "unowned" -> UNOWNED
                else -> AUTOMATIC
            }
        }
    }
}

data class SourceLocation(
    val line: Int = 1,
    val column: Int = 1,
    val file: String = "<input>"
) {
    override fun toString(): String = "$file:$line:$column"
}

sealed class ASTNode(open val loc: SourceLocation = SourceLocation())

data class TypeNode(
    override val loc: SourceLocation = SourceLocation(),
    val name: String = "Void",
    var ownership: OwnershipKind = OwnershipKind.AUTOMATIC,
    val isOptional: Boolean = false,
    val genericArgs: List<TypeNode> = emptyList()
) : ASTNode(loc) {
    override fun toString(): String {
        var res = name
        if (genericArgs.isNotEmpty()) {
            res += "[${genericArgs.joinToString(", ")}]"
        }
        if (isOptional) res += "?"
        if (ownership != OwnershipKind.AUTOMATIC) {
            res = "${ownership.keyword} $res"
        }
        return res
    }
}

sealed class ExprNode(override val loc: SourceLocation = SourceLocation()) : ASTNode(loc) {
    var inferredType: TypeNode? = null
}

data class LiteralExpr(
    override val loc: SourceLocation = SourceLocation(),
    val value: Any?,
    val typeName: String
) : ExprNode(loc)

data class IdentifierExpr(
    override val loc: SourceLocation = SourceLocation(),
    val name: String
) : ExprNode(loc)

data class BinaryExpr(
    override val loc: SourceLocation = SourceLocation(),
    val left: ExprNode,
    val op: String,
    val right: ExprNode
) : ExprNode(loc)

data class UnaryExpr(
    override val loc: SourceLocation = SourceLocation(),
    val op: String,
    val operand: ExprNode
) : ExprNode(loc)

data class CallExpr(
    override val loc: SourceLocation = SourceLocation(),
    val callee: ExprNode,
    val args: List<ExprNode> = emptyList()
) : ExprNode(loc)

data class MemberAccessExpr(
    override val loc: SourceLocation = SourceLocation(),
    val obj: ExprNode,
    val member: String
) : ExprNode(loc)

data class IndexExpr(
    override val loc: SourceLocation = SourceLocation(),
    val target: ExprNode,
    val index: ExprNode
) : ExprNode(loc)

data class ArrayLiteralExpr(
    override val loc: SourceLocation = SourceLocation(),
    val elements: List<ExprNode> = emptyList()
) : ExprNode(loc)

data class NewExpr(
    override val loc: SourceLocation = SourceLocation(),
    val typeName: String,
    val args: List<ExprNode> = emptyList(),
    val ownership: OwnershipKind = OwnershipKind.AUTOMATIC
) : ExprNode(loc)

data class WeakRefExpr(
    override val loc: SourceLocation = SourceLocation(),
    val expr: ExprNode
) : ExprNode(loc)

data class RangeExpr(
    override val loc: SourceLocation = SourceLocation(),
    val start: ExprNode,
    val end: ExprNode
) : ExprNode(loc)

sealed class StmtNode(override val loc: SourceLocation = SourceLocation()) : ASTNode(loc)

data class BlockStmt(
    override val loc: SourceLocation = SourceLocation(),
    val statements: MutableList<StmtNode> = mutableListOf()
) : StmtNode(loc)

data class VarDeclStmt(
    override val loc: SourceLocation = SourceLocation(),
    val name: String,
    val typeAnnotation: TypeNode? = null,
    val initializer: ExprNode? = null,
    val isConst: Boolean = false,
    var ownership: OwnershipKind = OwnershipKind.AUTOMATIC
) : StmtNode(loc)

data class AssignStmt(
    override val loc: SourceLocation = SourceLocation(),
    val target: ExprNode,
    val value: ExprNode
) : StmtNode(loc)

data class IfStmt(
    override val loc: SourceLocation = SourceLocation(),
    val condition: ExprNode,
    val thenBranch: BlockStmt,
    val elseBranch: BlockStmt? = null
) : StmtNode(loc)

data class WhileStmt(
    override val loc: SourceLocation = SourceLocation(),
    val condition: ExprNode,
    val body: BlockStmt
) : StmtNode(loc)

data class ForStmt(
    override val loc: SourceLocation = SourceLocation(),
    val varName: String,
    val iterable: ExprNode,
    val body: BlockStmt
) : StmtNode(loc)

data class ReturnStmt(
    override val loc: SourceLocation = SourceLocation(),
    val value: ExprNode? = null
) : StmtNode(loc)

data class DeferStmt(
    override val loc: SourceLocation = SourceLocation(),
    val body: BlockStmt
) : StmtNode(loc)

data class ExprStmt(
    override val loc: SourceLocation = SourceLocation(),
    val expr: ExprNode
) : StmtNode(loc)

data class ParamNode(
    override val loc: SourceLocation = SourceLocation(),
    val name: String,
    val typeAnnotation: TypeNode,
    val ownership: OwnershipKind = OwnershipKind.AUTOMATIC
) : ASTNode(loc)

data class FieldNode(
    override val loc: SourceLocation = SourceLocation(),
    val name: String,
    val typeAnnotation: TypeNode,
    var ownership: OwnershipKind = OwnershipKind.AUTOMATIC,
    val initializer: ExprNode? = null
) : ASTNode(loc)

data class FuncDecl(
    override val loc: SourceLocation = SourceLocation(),
    val name: String,
    val params: List<ParamNode> = emptyList(),
    val returnType: TypeNode = TypeNode(loc, "Void"),
    val body: BlockStmt,
    val isMethod: Boolean = false
) : ASTNode(loc)

data class StructDecl(
    override val loc: SourceLocation = SourceLocation(),
    val name: String,
    val fields: List<FieldNode> = emptyList()
) : ASTNode(loc)

data class ClassDecl(
    override val loc: SourceLocation = SourceLocation(),
    val name: String,
    val defaultOwnership: OwnershipKind = OwnershipKind.OWNED,
    val fields: List<FieldNode> = emptyList(),
    val initMethod: FuncDecl? = null,
    val deinitMethod: BlockStmt? = null,
    val methods: List<FuncDecl> = emptyList()
) : ASTNode(loc)

data class ProgramNode(
    override val loc: SourceLocation = SourceLocation(),
    val declarations: List<ASTNode> = emptyList()
) : ASTNode(loc)
